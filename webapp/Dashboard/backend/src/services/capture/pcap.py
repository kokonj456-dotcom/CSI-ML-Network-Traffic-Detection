"""Read captured packets offline and return completed flow records."""

from scapy.all import PcapReader

from .flows import FlowCollector, flow_record


def capture_flows(file, packet_limit=None):
    collector = FlowCollector()
    finished = []
    with PcapReader(str(file)) as capture:
        for frame, packet in enumerate(capture, 1):
            if packet_limit is not None and frame > packet_limit:
                raise ValueError(
                    f"Capture exceeds the {packet_limit:,} packet import limit."
                )
            completed = collector.push(packet, frame)
            if completed:
                finished.append(completed)
    finished.extend(collector.active.values())
    return [
        flow_record(flow) for flow in sorted(finished, key=lambda item: item["start"])
    ]
