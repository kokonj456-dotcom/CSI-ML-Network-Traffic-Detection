"""Read memory metrics for the capture process and host."""

import ctypes
import os
import sys


def process_memory():
    """Return process working set and machine RAM in MiB where available."""
    if os.name == "nt":

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ProcessMemoryCounters),
                ctypes.c_ulong,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
            kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
            if not psapi.GetProcessMemoryInfo(
                kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
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
    return sys.platform == "darwin"
