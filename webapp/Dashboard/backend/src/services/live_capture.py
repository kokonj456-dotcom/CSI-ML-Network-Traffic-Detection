"""Passive Npcap capture, bounded queues and live capacity metrics."""
import ctypes
import json
import os
from collections import deque
from ipaddress import ip_address
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic, process_time, time

from scapy.all import AsyncSniffer, conf

from .capture.flows import FlowCollector, flow_record


DEFAULT_SETTINGS = {
    "max_flows_per_second": 128,
    "packet_queue_capacity": 8192,
    "flow_queue_capacity": 8192,
}
QUEUE_PACKET_BYTES_ESTIMATE = 3072
QUEUE_FLOW_BYTES_ESTIMATE = 4096


def process_memory():
    """Return process working set and machine RAM in MiB where available."""
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        try:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
            kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
            if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                return None, None, None
            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            total = None
            used = None
            if kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
                total = status.ullTotalPhys / (1024 * 1024)
                used = (status.ullTotalPhys - status.ullAvailPhys) / (1024 * 1024)
            return counters.WorkingSetSize / (1024 * 1024), used, total
        except (AttributeError, OSError, ctypes.ArgumentError):
            return None, None, None
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / (1024 if sys_platform_is_macos() else 1024 * 1024), None, None
    except (ImportError, AttributeError, OSError):
        return None, None, None


def sys_platform_is_macos():
    import sys
    return sys.platform == "darwin"


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
        now = monotonic()
        elapsed = max(now - self._last_stats_time, 0.001)
        with self._stats_lock:
            flow_in_rate = max(0, self._flow_arrivals_total - self._last_arrivals) / elapsed
            flow_out_rate = max(0, self._processed_total - self._last_processed) / elapsed
            self._last_stats_time = now
            self._last_arrivals = self._flow_arrivals_total
            self._last_processed = self._processed_total
        cpu_elapsed = max(now - self._cpu_sample_time, 0.001)
        cpu_now = process_time()
        cores = os.cpu_count() or 1
        self._cpu_percent = max(0.0, (cpu_now - self._cpu_sample) / cpu_elapsed / cores * 100)
        self._cpu_sample_time, self._cpu_sample = now, cpu_now
        with self.settings_lock:
            settings = dict(self.settings)
        packet_depth = self.packets.qsize()
        flow_depth = len(self.pending_flows)
        queue_elapsed = max(now - self._last_queue_sample_time, 0.001)
        packet_growth = (packet_depth - self._last_packet_depth) / queue_elapsed
        flow_growth = (flow_depth - self._last_flow_depth) / queue_elapsed
        self._last_queue_sample_time, self._last_packet_depth, self._last_flow_depth = now, packet_depth, flow_depth
        packet_util = packet_depth / settings["packet_queue_capacity"]
        flow_util = flow_depth / settings["flow_queue_capacity"]
        memory_mb, system_used_mb, total_memory_mb = process_memory()
        input_per_second = flow_in_rate
        configured_rate = settings["max_flows_per_second"]
        target_rate = configured_rate or input_per_second
        avg_cpu_per_flow = (self._inference_cpu_seconds / self._inference_flows) if self._inference_flows else None
        estimated_cpu = (min(100.0, avg_cpu_per_flow * target_rate / cores * 100)
                         if avg_cpu_per_flow is not None else None)
        queue_ram_mb = (settings["packet_queue_capacity"] * QUEUE_PACKET_BYTES_ESTIMATE +
                        settings["flow_queue_capacity"] * QUEUE_FLOW_BYTES_ESTIMATE) / (1024 * 1024)
        baseline_ram_mb = system_used_mb if system_used_mb is not None else memory_mb
        projected_ram_mb = baseline_ram_mb + queue_ram_mb if baseline_ram_mb is not None else None
        queue_fill_times = []
        if packet_growth > 0:
            queue_fill_times.append(max(0, settings["packet_queue_capacity"] - packet_depth) / packet_growth)
        if flow_growth > 0:
            queue_fill_times.append(max(0, settings["flow_queue_capacity"] - flow_depth) / flow_growth)
        seconds_to_full = min(queue_fill_times) if queue_fill_times else None
        overloaded = (packet_util >= .85 or flow_util >= .85 or
                      (estimated_cpu is not None and estimated_cpu >= 85) or
                      (projected_ram_mb is not None and total_memory_mb and projected_ram_mb / total_memory_mb >= .85))
        return {
            "running": self.ready.is_set() and bool(self.thread and self.thread.is_alive()),
            "interface": self.interface, "address": self.address, "direction": self.direction,
            "capture_https": self.capture_https, "error": self.error,
            "saved": self.saved, "dropped": self.dropped, "dropped_flows": self.dropped_flows,
            "settings": settings,
            "queues": {
                "packets": {"waiting": packet_depth, "capacity": settings["packet_queue_capacity"], "utilization": packet_util},
                "flows": {"waiting": flow_depth, "capacity": settings["flow_queue_capacity"], "utilization": flow_util},
            },
            "rates": {"flows_in_per_second": round(flow_in_rate, 2), "flows_processed_per_second": round(flow_out_rate, 2)},
            "resources": {"process_cpu_percent": round(self._cpu_percent, 1),
                          "estimated_model_cpu_percent": round(estimated_cpu, 1) if estimated_cpu is not None else None,
                          "process_ram_mb": round(memory_mb, 1) if memory_mb is not None else None,
                          "system_ram_used_mb": round(system_used_mb, 1) if system_used_mb is not None else None,
                          "estimated_ram_at_full_queues_mb": round(projected_ram_mb, 1) if projected_ram_mb is not None else None,
                          "system_ram_mb": round(total_memory_mb, 1) if total_memory_mb is not None else None,
                          "queue_ram_estimate_mb": round(queue_ram_mb, 1)},
            "overload_risk": overloaded, "seconds_to_queue_full": round(seconds_to_full, 1) if seconds_to_full is not None else None,
            "overflow_policy": "Drop newest and count it",
        }

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
        collector = FlowCollector(evidence=False, max_flows=8192)

        def enqueue(flow, target):
            if self.direction != "both" and ip_address(flow["dst"][0]) != target:
                return
            with self._stats_lock:
                self._flow_arrivals_total += 1
            with self.settings_lock:
                capacity = self.settings["flow_queue_capacity"]
            if len(self.pending_flows) >= capacity:
                self.dropped_flows += 1
                return
            self.pending_flows.append(flow)

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
                        enqueue(completed, target)
                    for _ in range(4095):
                        try:
                            packet = self.packets.get_nowait()
                        except Empty:
                            break
                        completed = collector.push(packet)
                        if completed:
                            enqueue(completed, target)
                if monotonic() < next_flush:
                    continue
                next_flush = monotonic() + 1
                if collector.skipped:
                    self.dropped_flows += collector.skipped
                    collector.skipped = 0
                for flow in collector.drain(time()):
                    enqueue(flow, target)
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
                    self.store.save_live(getattr(interface, "name", str(interface)), batch, predictions)
                    self._inference_cpu_seconds += cpu_used
                    self._inference_flows += len(batch)
                    self.saved += len(batch)
                    allowance -= len(batch)
                    with self._stats_lock:
                        self._processed_total += len(batch)
        except Exception as error:
            self.error = f"{type(error).__name__}: live capture stopped. Check Npcap, the interface and MySQL."
        finally:
            self.ready.clear()
            if sniffer and sniffer.running and hasattr(sniffer, "stop_cb"):
                sniffer.stop()
