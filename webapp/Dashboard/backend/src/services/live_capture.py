"""Passive Npcap capture, bounded queues and live capacity metrics."""
import json
from collections import deque
from ipaddress import ip_address
from itertools import groupby
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic, process_time, time

from scapy.all import AsyncSniffer, conf

from .capture.flows import FlowCollector, flow_record
from .capture.metrics import capture_snapshot


DEFAULT_SETTINGS = {
    "max_flows_per_second": 128,
    "packet_queue_capacity": 8192,
    "flow_queue_capacity": 8192,
}
LOCALHOST_IPV4 = ip_address("127.0.0.1")


class LiveCapture:
    def __init__(self, store, manager, interface=None, address=None, direction="inbound", capture_https=True,
                 settings_path=None):
        self.store = store
        self.manager = manager
        self.interface = interface
        self.address = address
        self.direction = direction
        self.capture_https = capture_https
        self.settings_path = settings_path
        self.settings_lock = Lock()
        self.settings = self.load_settings()
        self.packets = Queue(maxsize=self.settings["packet_queue_capacity"])
        self.pending_flows = deque()
        self.stop_event = Event()
        self.ready = Event()
        self.thread = None
        self.error = None
        self.saved = 0
        self.dropped = 0
        self.dropped_flows = 0
        self._stats_lock = Lock()
        self._flow_arrivals_total = 0
        self._processed_total = 0
        self._last_stats_time = monotonic()
        self._last_arrivals = 0
        self._last_processed = 0
        self._cpu_sample_time = monotonic()
        self._cpu_sample = process_time()
        self._cpu_percent = None
        self._inference_cpu_seconds = 0.0
        self._inference_flows = 0
        self._last_queue_sample_time = monotonic()
        self._last_packet_depth = 0
        self._last_flow_depth = 0

    def load_settings(self):
        settings = dict(DEFAULT_SETTINGS)
        if self.settings_path and self.settings_path.is_file():
            try:
                saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
                for key in settings:
                    if key in saved:
                        settings[key] = int(saved[key])
            except (OSError, ValueError, TypeError):
                pass
        try:
            return self.validate_settings(settings)
        except (KeyError, ValueError, TypeError):
            return dict(DEFAULT_SETTINGS)

    @staticmethod
    def validate_settings(settings):
        limits = {"max_flows_per_second": (0, 100000),
                  "packet_queue_capacity": (64, 262144),
                  "flow_queue_capacity": (64, 131072)}
        result = {}
        for key, (minimum, maximum) in limits.items():
            value = int(settings[key])
            if not minimum <= value <= maximum:
                raise ValueError(f"{key} must be between {minimum} and {maximum}.")
            result[key] = value
        return result

    def configure(self, settings):
        with self.settings_lock:
            updated = self.validate_settings({**self.settings, **settings})
            if self.settings_path:
                self.settings_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
                temporary.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
                temporary.replace(self.settings_path)
            self.settings = updated
            with self.packets.mutex:
                self.packets.maxsize = updated["packet_queue_capacity"]
        return dict(updated)

    def snapshot(self):
        return capture_snapshot(self, LOCALHOST_IPV4)

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

    def enqueue_flow(self, flow, targets):
        if self.direction != "both" and ip_address(flow["dst"][0]) not in targets:
            return
        with self._stats_lock:
            self._flow_arrivals_total += 1
        with self.settings_lock:
            capacity = self.settings["flow_queue_capacity"]
        if len(self.pending_flows) >= capacity:
            self.dropped_flows += 1
            return
        self.pending_flows.append(flow)

    def capture_filter(self, target):
        local_filter = f"host {LOCALHOST_IPV4}"
        # Saving a flow to local MySQL must not generate another captured flow.
        database = self.store.settings
        if database.get("host") in {"localhost", "127.0.0.1"}:
            local_filter += f" and not tcp port {int(database['port'])}"
        capture_filter = f"({local_filter})"
        if target != LOCALHOST_IPV4:
            capture_filter = f"(host {target} or {capture_filter})"
        if not self.capture_https:
            capture_filter += " and not (tcp port 443 or tcp port 8443 or udp port 443)"
        return capture_filter

    def start_capture_adapters(self, interfaces, capture_filter, sniffers):
        # Let each adapter read independently while sharing the bounded packet queue.
        adapter_ready = []
        for adapter in interfaces:
            started = Event()
            sniffer = AsyncSniffer(iface=adapter, filter=capture_filter, store=False,
                                   prn=self.receive, started_callback=started.set)
            sniffer.start()
            sniffers.append(sniffer)
            adapter_ready.append(started)
        return adapter_ready

    def collect_packets(self, collector, targets):
        try:
            packet = self.packets.get(timeout=.25)
        except Empty:
            packet = None
        if packet is not None:
            completed = collector.push(packet)
            if completed:
                self.enqueue_flow(completed, targets)
            for _ in range(4095):
                try:
                    packet = self.packets.get_nowait()
                except Empty:
                    break
                completed = collector.push(packet)
                if completed:
                    self.enqueue_flow(completed, targets)

    def score_pending_flows(self, interface, loopback):
        with self.settings_lock:
            rate_limit = self.settings["max_flows_per_second"]
        allowance = rate_limit or len(self.pending_flows)
        while self.pending_flows and allowance > 0:
            batch = []
            while self.pending_flows and len(batch) < min(128, allowance):
                batch.append(flow_record(self.pending_flows.popleft()))
            if not batch:
                break
            cpu_start = process_time()
            predictions = self.manager.predictor.predict([flow["raw"] for flow in batch], explain=True)
            cpu_used = process_time() - cpu_start
            def capture_interface(pair):
                record, _ = pair
                if str(LOCALHOST_IPV4) in (record["src"], record["dst"]):
                    return loopback.name
                return getattr(interface, "name", str(interface))

            for interface_name, group in groupby(zip(batch, predictions, strict=True), capture_interface):
                records, results = zip(*group)
                self.store.save_live(interface_name, records, results)
            self._inference_cpu_seconds += cpu_used
            self._inference_flows += len(batch)
            self.saved += len(batch)
            allowance -= len(batch)
            with self._stats_lock:
                self._processed_total += len(batch)

    def run(self):
        sniffers = []
        collector = FlowCollector(evidence=False, max_flows=8192)

        try:
            target = ip_address(self.address)
            if self.direction not in ("inbound", "both"):
                raise ValueError("Unsupported capture direction.")
            interface = conf.ifaces.dev_from_index(int(self.interface)) if self.interface.isdecimal() else self.interface
            targets = {target, LOCALHOST_IPV4}
            loopback = conf.ifaces.dev_from_networkname(conf.loopback_name)
            interfaces = [loopback] if target == LOCALHOST_IPV4 else [interface, loopback]
            capture_filter = self.capture_filter(target)
            adapter_ready = self.start_capture_adapters(interfaces, capture_filter, sniffers)
            next_flush = monotonic()
            while not self.stop_event.is_set():
                for sniffer in sniffers:
                    if not sniffer.thread.is_alive():
                        sniffer.join()
                        raise RuntimeError("Capture stopped unexpectedly.")
                if all(started.is_set() for started in adapter_ready):
                    self.ready.set()
                self.collect_packets(collector, targets)
                if monotonic() < next_flush:
                    continue
                next_flush = monotonic() + 1
                if collector.skipped:
                    self.dropped_flows += collector.skipped
                    collector.skipped = 0
                for flow in collector.drain(time()):
                    self.enqueue_flow(flow, targets)
                self.score_pending_flows(interface, loopback)
        except Exception as error:
            self.error = f"{type(error).__name__}: live capture stopped. Check Npcap, the interface and MySQL."
        finally:
            self.ready.clear()
            for sniffer in sniffers:
                if sniffer.running and hasattr(sniffer, "stop_cb"):
                    sniffer.stop()
