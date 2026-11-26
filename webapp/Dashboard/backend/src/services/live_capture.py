"""Passive Npcap capture and flow inference on a selected interface."""
from collections import deque
from ipaddress import ip_address
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic, time

from scapy.all import AsyncSniffer, conf

from .capture.flows import FlowCollector, flow_record


class LiveCapture:
    def __init__(self, store, manager, interface=None, address=None, direction="inbound", capture_https=True):
        self.store = store
        self.manager = manager
        self.interface = interface
        self.address = address
        self.direction = direction
        self.capture_https = capture_https
        self.packets = Queue(maxsize=8192)
        self.stop_event = Event()
        self.ready = Event()
        self.thread = None
        self.error = None
        self.saved = 0
        self.dropped = 0
        self.dropped_flows = 0

    def snapshot(self):
        return {"running": self.ready.is_set() and bool(self.thread and self.thread.is_alive()),
                "interface": self.interface, "address": self.address, "direction": self.direction,
                "capture_https": self.capture_https, "error": self.error,
                "saved": self.saved, "dropped": self.dropped, "dropped_flows": self.dropped_flows}

    def start(self):
        if not self.interface or not self.address:
            return
        if self.store is None:
            self.error = "Configure MySQL to enable live capture."
            return
        self.thread = Thread(target=self.run, name="flowwatch-capture", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=12)

    def receive(self, packet):
        try:
            self.packets.put_nowait(packet)
        except Full:
            self.dropped += 1

    def run(self):
        sniffer = None
        pending = deque()
        collector = FlowCollector(evidence=False, max_flows=8192)

        def enqueue(flow):
            if len(pending) < 8192:
                pending.append(flow)
            else:
                self.dropped_flows += 1

        try:
            target = ip_address(self.address)
            if self.direction not in ("inbound", "both"):
                raise ValueError("Unsupported capture direction.")
            interface = conf.ifaces.dev_from_index(int(self.interface)) if self.interface.isdecimal() else self.interface
            capture_filter = f"host {target}"
            if not self.capture_https:
                capture_filter += " and not (tcp port 443 or tcp port 8443 or udp port 443)"
            sniffer = AsyncSniffer(iface=interface, filter=capture_filter, store=False,
                                   prn=self.receive, started_callback=self.ready.set)
            sniffer.start()
            next_flush = monotonic()
            while not self.stop_event.is_set():
                if not sniffer.thread.is_alive():
                    sniffer.join()
                    raise RuntimeError("Capture stopped unexpectedly.")
                try:
                    packet = self.packets.get(timeout=.25)
                except Empty:
                    packet = None
                if packet is not None:
                    completed = collector.push(packet)
                    if completed:
                        enqueue(completed)
                if monotonic() < next_flush:
                    continue
                next_flush = monotonic()+1
                if collector.skipped:
                    self.dropped_flows += collector.skipped
                    collector.skipped = 0
                for flow in collector.drain(time()):
                    enqueue(flow)
                batch = []
                while pending and len(batch) < 128:
                    flow = pending.popleft()
                    if self.direction == "both" or ip_address(flow["dst"][0]) == target:
                        batch.append(flow_record(flow))
                if batch:
                    records = self.manager.predictor.predict([flow["raw"] for flow in batch], explain=True)
                    self.store.save_live(getattr(interface, "name", str(interface)), batch, records)
                    self.saved += len(batch)
        except Exception as error:
            self.error = f"{type(error).__name__}: live capture stopped. Check Npcap, the interface and MySQL."
        finally:
            self.ready.clear()
            if sniffer and sniffer.running and hasattr(sniffer, "stop_cb"):
                sniffer.stop()
