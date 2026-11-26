"""Combine packets into bidirectional flows and prepare model inputs."""
from scapy.all import DNS, ICMP, IP, IPv6, TCP, UDP

from .protocols import SERVICES, dns_event, has_http_start_line, has_tls_handshake_header, web_observation

TCP_FIN = 0x01
TCP_SYN = 0x02
TCP_RST = 0x04
TCP_ACK = 0x10
TCP_IDLE_SECONDS = 60
OTHER_IDLE_SECONDS = 15
MAX_LIVE_FLOW_SECONDS = 120


def transport_payload_length(payload, network, tcp, udp):
    """Count observed transport payload bytes up to the header's declared length."""
    observed = len(payload)
    if udp:
        return min(observed, max(0, int(udp.len or 8) - 8))
    if isinstance(network, IP):
        ip_header = int(network.ihl or 5) * 4
        transport_header = int(tcp.dataofs or 5) * 4 if tcp else 8
        return min(observed, max(0, int(network.len or 0) - ip_header - transport_header))
    return observed


class FlowCollector:
    def __init__(self, evidence=True, max_flows=None):
        self.active = {}
        self.evidence = evidence
        self.max_flows = max_flows
        self.skipped = 0

    def push(self, packet, frame=None):
        completed = None
        network = packet.getlayer(IP) or packet.getlayer(IPv6)
        if network is None:
            return None
        tcp, udp, icmp = packet.getlayer(TCP), packet.getlayer(UDP), packet.getlayer(ICMP)
        transport = tcp or udp or icmp
        if transport is None:
            return None
        protocol = "tcp" if tcp else "udp" if udp else "icmp"
        src = (network.src, getattr(transport, "sport", None))
        dst = (network.dst, getattr(transport, "dport", None))
        key = (protocol, frozenset((src, dst)))
        timestamp = float(packet.time)
        flags = int(tcp.flags) if tcp else 0
        flow = self.active.get(key)
        initial_syn = bool(flags & TCP_SYN and not flags & TCP_ACK)
        syn_ack = bool(flags & TCP_SYN and flags & TCP_ACK)
        idle_seconds = TCP_IDLE_SECONDS if tcp else OTHER_IDLE_SECONDS
        if flow and (timestamp - flow["end"] > idle_seconds or (initial_syn and flow["terminated"])):
            completed = self.active.pop(key)
            flow = None
        if flow is None:
            if self.max_flows is not None and len(self.active) >= self.max_flows:
                self.skipped += 1
                return completed
            # SYN-ACK as the first observed packet indicates the other endpoint initiated.
            origin, destination = (dst, src) if syn_ack else (src, dst)
            flow = {
                "src": origin, "dst": destination, "start": timestamp, "end": timestamp,
                "protocol": protocol, "frames": [], "bytes": [0, 0], "packets": [0, 0],
                "syn": False, "syn_ack": False, "reset": False, "terminated": False,
                "dns_events": [], "http": False, "tls": False,
            }
            self.active[key] = flow
        direction_index = 0 if src == flow["src"] else 1
        flow["end"] = max(flow["end"], timestamp)
        if self.evidence:
            flow["frames"].append(frame)
        payload = bytes(transport.payload)
        if tcp and payload:
            flow["http"] |= has_http_start_line(payload)
            flow["tls"] |= has_tls_handshake_header(payload)
        flow["bytes"][direction_index] += transport_payload_length(payload, network, tcp, udp)
        flow["packets"][direction_index] += 1
        flow["syn"] |= initial_syn
        flow["syn_ack"] |= syn_ack
        flow["reset"] |= bool(flags & TCP_RST)
        flow["terminated"] |= bool(flags & (TCP_FIN | TCP_RST))
        dns = packet.getlayer(DNS)
        if dns is not None and (self.evidence or len(flow["dns_events"]) < 32):
            flow["dns_events"].append(dns_event(dns, timestamp, frame))
        return completed

    def drain(self, now):
        for key, flow in list(self.active.items()):
            if flow["terminated"]:
                idle = 2
            elif flow["syn"] and not flow["packets"][1]:
                idle = 8
            else:
                idle = TCP_IDLE_SECONDS if flow["protocol"] == "tcp" else OTHER_IDLE_SECONDS
            if now-flow["end"] >= idle or now-flow["start"] >= MAX_LIVE_FLOW_SECONDS:
                yield self.active.pop(key)


def connection_state(flow):
    if flow["reset"]:
        return "reset"
    if flow["syn"] and flow["syn_ack"]:
        return "established"
    if flow["syn"] and not flow["packets"][1]:
        return "no-reply"
    return "other"


def flow_record(flow):
    src, sport = flow["src"]
    dst, dport = flow["dst"]
    protocol = flow["protocol"]
    service_group = "other"
    if flow["dns_events"]:
        service_group = "dns"
    elif protocol in ("tcp", "udp"):
        service_group = SERVICES.get(dport, "other")
    state = connection_state(flow)
    raw = {
        "duration": flow["end"] - flow["start"],
        "bytes_forward": flow["bytes"][0],
        "bytes_backward": flow["bytes"][1],
        "protocol": protocol,
        "service_group": service_group,
        "conn_state_group": state,
    }
    return {
        "src":src,"sport":sport,"dst":dst,"dport":dport,
        "timestamp":round(flow["start"]*1000),"packets":sum(flow["packets"]),
        "started_at":flow["start"], "ended_at":flow["end"],
        "packets_forward":flow["packets"][0], "packets_backward":flow["packets"][1],
        "protocol_events":flow["dns_events"],
        "protocol_observation":web_observation(flow),
        "frames":flow["frames"],
        "service_basis":"decoded DNS" if flow["dns_events"] else "port hint" if service_group!="other" else "unavailable",
        "state_basis":"observed TCP flags" if state!="other" else "unavailable",
        "raw":raw,
    }
