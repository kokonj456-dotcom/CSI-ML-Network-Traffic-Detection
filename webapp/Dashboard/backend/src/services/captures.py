"""Compatibility imports for packet capture callers."""
from .capture.flows import FlowCollector, flow_record
from .capture.pcap import capture_flows

__all__ = ["FlowCollector", "capture_flows", "flow_record"]
