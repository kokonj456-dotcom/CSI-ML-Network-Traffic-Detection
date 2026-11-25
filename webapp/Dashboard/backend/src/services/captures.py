"""Summarize observed packets without transmitting them."""
import re

from scapy.all import DNS, ICMP, IP, IPv6, TCP, UDP, PcapReader

SERVICES = {20:"ftp",21:"ftp",22:"ssh",25:"smtp",53:"dns",80:"http",443:"https_ssl",8080:"http",8443:"https_ssl"}
HTTP_LINE = re.compile(rb"(?:(GET|HEAD|POST|PUT|DELETE|CONNECT|OPTIONS|TRACE|PATCH) [^\r\n ]+ HTTP/1\.[01]|HTTP/1\.[01] [1-5]\d\d(?: [^\r\n]*)?)\r?\n")


def web_observation(flow):
    if flow["dns_events"]:
        return {"label": "DNS", "basis": "Decoded DNS"}
    ports = {flow["src"][1], flow["dst"][1]}
    if flow["http"]:
        return {"label": "HTTP", "basis": "Observed HTTP/1.x request or response line"}
    if flow["tls"]:
        return {"label": "HTTPS/TLS" if ports & {443, 8443} else "TLS", "basis": "Observed TLS handshake header"}
    if flow["protocol"] == "udp" and 443 in ports:
        return {"label": "QUIC?", "basis": "UDP port 443. QUIC is possible."}
    if flow["protocol"] == "tcp" and ports & {443, 8443}:
        return {"label": "HTTPS/TLS", "basis": "TCP port hint"}
    if flow["protocol"] == "tcp" and ports & {80, 8080}:
        return {"label": "HTTP", "basis": "TCP port hint"}
    return None


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
        src = (network.src, getattr(transport,"sport",None))
        dst = (network.dst, getattr(transport,"dport",None))
        key = (protocol, frozenset((src,dst)))
        at = float(packet.time)
        flags = int(tcp.flags) if tcp else 0
        flow = self.active.get(key)
        new_syn = bool(flags & 2 and not flags & 16)
        if flow and (at-flow["end"] > (60 if tcp else 15) or (new_syn and flow["terminated"])):
            completed = self.active.pop(key)
            flow = None
        if flow is None:
            if self.max_flows is not None and len(self.active) >= self.max_flows:
                self.skipped += 1
                return completed
            # SYN-ACK as the first observed packet indicates the other endpoint initiated.
            direction = (dst,src) if flags & 2 and flags & 16 else (src,dst)
            flow = {"src":direction[0],"dst":direction[1],"start":at,"end":at,"protocol":protocol,
                    "frames":[],"bytes":[0,0],"packets":[0,0],"syn":False,"syn_ack":False,
                    "reset":False,"terminated":False,"dns_events":[],"http":False,"tls":False}
            self.active[key] = flow
        index = 0 if src == flow["src"] else 1
        flow["end"] = max(flow["end"],at)
        if self.evidence:
            flow["frames"].append(frame)
        # Limit to observed transport bytes and exclude Ethernet padding.
        payload = bytes(transport.payload)
        observed = len(payload)
        if tcp and payload:
            flow["http"] |= bool(HTTP_LINE.match(payload[:2048]))
            flow["tls"] |= (len(payload) >= 9 and payload[0] == 22 and payload[1] == 3
                            and payload[2] <= 3 and payload[5] in (1, 2)
                            and 4 <= int.from_bytes(payload[3:5], "big") <= 16384)
        if udp:
            observed = min(observed,max(0,int(udp.len or 8)-8))
        elif isinstance(network, IP):
            header = int(network.ihl or 5)*4 + (int(tcp.dataofs or 5)*4 if tcp else 8)
            observed = min(observed,max(0,int(network.len or 0)-header))
        flow["bytes"][index] += observed
        flow["packets"][index] += 1
        flow["syn"] |= new_syn
        flow["syn_ack"] |= bool(flags & 2 and flags & 16)
        flow["reset"] |= bool(flags & 4)
        flow["terminated"] |= bool(flags & 5)
        dns = packet.getlayer(DNS)
        if dns is not None and (self.evidence or len(flow["dns_events"]) < 32):
            question = dns.qd[0] if dns.qd else None
            flow["dns_events"].append({
                "at": at, "frame": frame, "protocol": "dns",
                "details": {
                    "transaction_id": int(dns.id),
                    "response": bool(dns.qr),
                    "response_code": int(dns.rcode),
                    "question": question.qname.decode("utf-8", errors="replace") if question else None,
                    "question_type": int(question.qtype) if question else None,
                },
            })
        return completed

    def drain(self, now):
        for key, flow in list(self.active.items()):
            if flow["terminated"]:
                idle = 2
            elif flow["syn"] and not flow["packets"][1]:
                idle = 8
            else:
                idle = 60 if flow["protocol"] == "tcp" else 15
            if now-flow["end"] >= idle or now-flow["start"] >= 120:
                yield self.active.pop(key)


def flow_record(flow):
    src,sport=flow["src"]
    dst,dport=flow["dst"]
    hint="dns" if flow["dns_events"] else SERVICES.get(dport,"other") if flow["protocol"] in ("tcp","udp") else "other"
    conn="reset" if flow["reset"] else "established" if flow["syn"] and flow["syn_ack"] else \
        "no-reply" if flow["syn"] and not flow["packets"][1] else "other"
    return {
        "src":src,"sport":sport,"dst":dst,"dport":dport,
        "timestamp":round(flow["start"]*1000),"packets":sum(flow["packets"]),
        "started_at":flow["start"], "ended_at":flow["end"],
        "packets_forward":flow["packets"][0], "packets_backward":flow["packets"][1],
        "protocol_events":flow["dns_events"],
        "protocol_observation":web_observation(flow),
        "frames":flow["frames"],"service_basis":"decoded DNS" if flow["dns_events"] else "port hint" if hint!="other" else "unavailable",
        "state_basis":"observed TCP flags" if conn!="other" else "unavailable",
        "raw":{"duration":flow["end"]-flow["start"],"bytes_forward":flow["bytes"][0],"bytes_backward":flow["bytes"][1],
               "protocol":flow["protocol"],"service_group":hint,"conn_state_group":conn},
    }


def capture_flows(file, packet_limit=None):
    collector = FlowCollector()
    finished = []
    with PcapReader(str(file)) as capture:
        for frame, packet in enumerate(capture, 1):
            if packet_limit is not None and frame > packet_limit:
                raise ValueError(f"Capture exceeds the {packet_limit:,} packet import limit.")
            completed = collector.push(packet, frame)
            if completed:
                finished.append(completed)
    finished.extend(collector.active.values())
    return [flow_record(flow) for flow in sorted(finished, key=lambda item: item["start"])]
