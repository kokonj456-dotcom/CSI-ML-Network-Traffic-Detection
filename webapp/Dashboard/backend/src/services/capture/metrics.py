"""Build the live capture status and queue capacity report."""
import os
from time import monotonic, process_time

from .memory import process_memory


QUEUE_PACKET_BYTES_ESTIMATE = 3072
QUEUE_FLOW_BYTES_ESTIMATE = 4096


def capture_snapshot(capture, loopback_address):
    now = monotonic()
    elapsed = max(now - capture._last_stats_time, 0.001)
    with capture._stats_lock:
        flow_in_rate = max(0, capture._flow_arrivals_total - capture._last_arrivals) / elapsed
        flow_out_rate = max(0, capture._processed_total - capture._last_processed) / elapsed
        capture._last_stats_time = now
        capture._last_arrivals = capture._flow_arrivals_total
        capture._last_processed = capture._processed_total
    cpu_elapsed = max(now - capture._cpu_sample_time, 0.001)
    cpu_now = process_time()
    cores = os.cpu_count() or 1
    capture._cpu_percent = max(0.0, (cpu_now - capture._cpu_sample) / cpu_elapsed / cores * 100)
    capture._cpu_sample_time, capture._cpu_sample = now, cpu_now
    with capture.settings_lock:
        settings = dict(capture.settings)
    packet_depth = capture.packets.qsize()
    flow_depth = len(capture.pending_flows)
    queue_elapsed = max(now - capture._last_queue_sample_time, 0.001)
    packet_growth = (packet_depth - capture._last_packet_depth) / queue_elapsed
    flow_growth = (flow_depth - capture._last_flow_depth) / queue_elapsed
    capture._last_queue_sample_time, capture._last_packet_depth, capture._last_flow_depth = now, packet_depth, flow_depth
    packet_util = packet_depth / settings["packet_queue_capacity"]
    flow_util = flow_depth / settings["flow_queue_capacity"]
    memory_mb, system_used_mb, total_memory_mb = process_memory()
    input_per_second = flow_in_rate
    configured_rate = settings["max_flows_per_second"]
    target_rate = configured_rate or input_per_second
    avg_cpu_per_flow = (capture._inference_cpu_seconds / capture._inference_flows) if capture._inference_flows else None
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
        "running": capture.ready.is_set() and bool(capture.thread and capture.thread.is_alive()),
        "interface": capture.interface, "address": capture.address, "direction": capture.direction,
        "addresses": list(dict.fromkeys([capture.address, str(loopback_address)])) if capture.address else [],
        "capture_https": capture.capture_https, "error": capture.error,
        "saved": capture.saved, "dropped": capture.dropped, "dropped_flows": capture.dropped_flows,
        "settings": settings,
        "queues": {
            "packets": {"waiting": packet_depth, "capacity": settings["packet_queue_capacity"], "utilization": packet_util},
            "flows": {"waiting": flow_depth, "capacity": settings["flow_queue_capacity"], "utilization": flow_util},
        },
        "rates": {"flows_in_per_second": round(flow_in_rate, 2), "flows_processed_per_second": round(flow_out_rate, 2)},
        "resources": {"process_cpu_percent": round(capture._cpu_percent, 1),
                      "estimated_model_cpu_percent": round(estimated_cpu, 1) if estimated_cpu is not None else None,
                      "process_ram_mb": round(memory_mb, 1) if memory_mb is not None else None,
                      "system_ram_used_mb": round(system_used_mb, 1) if system_used_mb is not None else None,
                      "estimated_ram_at_full_queues_mb": round(projected_ram_mb, 1) if projected_ram_mb is not None else None,
                      "system_ram_mb": round(total_memory_mb, 1) if total_memory_mb is not None else None,
                      "queue_ram_estimate_mb": round(queue_ram_mb, 1)},
        "overload_risk": overloaded, "seconds_to_queue_full": round(seconds_to_full, 1) if seconds_to_full is not None else None,
        "overflow_policy": "Drop newest and count it",
    }
