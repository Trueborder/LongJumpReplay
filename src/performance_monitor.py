from __future__ import annotations

from collections import deque
import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import statistics
import time

from .models import BufferStats, CaptureStats


def _memory_usage() -> tuple[float, float]:
    """Return process working-set MB and total system RAM usage percent."""
    if os.name != "nt":
        try:
            import resource

            value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return value / (1024.0 if value > 1024 * 1024 else 1.0), 0.0
        except (ImportError, OSError):
            return 0.0, 0.0

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = (
            ("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t), ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t), ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t), ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t), ("peak_pagefile_usage", ctypes.c_size_t),
            ("private_usage", ctypes.c_size_t),
        )

    class MemoryStatus(ctypes.Structure):
        _fields_ = (
            ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        )

    process_mb = system_percent = 0.0
    try:
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        get_process_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory.argtypes = (ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong)
        get_process_memory.restype = ctypes.c_int
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if get_process_memory(get_current_process(), ctypes.byref(counters), counters.cb):
            process_mb = counters.working_set_size / 1024 ** 2
    except (AttributeError, OSError):
        pass
    try:
        memory_status = ctypes.windll.kernel32.GlobalMemoryStatusEx
        memory_status.argtypes = (ctypes.POINTER(MemoryStatus),)
        memory_status.restype = ctypes.c_int
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if memory_status(ctypes.byref(status)):
            system_percent = float(status.memory_load)
    except (AttributeError, OSError):
        pass
    return process_mb, system_percent


@dataclass(frozen=True, slots=True)
class PerformanceSample:
    monotonic: float
    capture_fps: float
    encode_fps: float
    queue_depth: int
    queue_drops: int
    read_failures: int
    encode_failures: int
    buffer_seconds: float
    buffer_memory_mb: float
    cache_gb: float
    disk_free_gb: float
    ui_p95_ms: float
    cpu_percent: float
    process_ram_mb: float
    system_ram_percent: float


@dataclass(frozen=True, slots=True)
class MetricSummary:
    current: float
    average_60s: float | None
    average_10m: float | None


class PerformanceMonitor:
    """Session-only one-second health history for the Performance tab."""

    def __init__(self, storage_path: Path, max_samples: int = 600) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.samples: deque[PerformanceSample] = deque(maxlen=max(60, max_samples))
        self._last_sample_at = 0.0
        self._last_cpu_wall = time.perf_counter()
        self._last_cpu_time = time.process_time()

    def sample(
        self,
        capture: CaptureStats,
        buffer: BufferStats,
        *,
        cache_bytes: int,
        ui_p95_ms: float,
        capture_active: bool = True,
    ) -> PerformanceSample | None:
        now = time.monotonic()
        if now - self._last_sample_at < 1.0:
            return None
        self._last_sample_at = now
        try:
            free = shutil.disk_usage(self.storage_path).free / 1024 ** 3
        except OSError:
            free = 0.0
        cpu_wall = time.perf_counter()
        cpu_time = time.process_time()
        elapsed = max(1e-6, cpu_wall - self._last_cpu_wall)
        cpu_percent = min(100.0, max(0.0, (cpu_time - self._last_cpu_time) / elapsed * 100.0 / max(1, os.cpu_count() or 1)))
        self._last_cpu_wall, self._last_cpu_time = cpu_wall, cpu_time
        process_ram_mb, system_ram_percent = _memory_usage()
        item = PerformanceSample(
            monotonic=now,
            # CaptureStats retains the last rolling FPS after a worker stops.
            # Record an explicit zero for paused/stopped capture so the graph
            # reflects the current camera state instead of the stale reading.
            capture_fps=capture.capture_fps if capture_active else 0.0,
            encode_fps=capture.encode_fps if capture_active else 0.0,
            queue_depth=capture.queue_depth, queue_drops=capture.queue_drops,
            read_failures=capture.read_failures, encode_failures=capture.encode_failures,
            buffer_seconds=buffer.duration_seconds, buffer_memory_mb=buffer.memory_bytes / 1024 ** 2,
            cache_gb=cache_bytes / 1024 ** 3, disk_free_gb=free, ui_p95_ms=float(ui_p95_ms),
            cpu_percent=cpu_percent, process_ram_mb=process_ram_mb,
            system_ram_percent=system_ram_percent,
        )
        self.samples.append(item)
        return item

    def summary(self, field: str) -> MetricSummary:
        if not self.samples:
            return MetricSummary(0.0, None, None)
        current = float(getattr(self.samples[-1], field))
        now = self.samples[-1].monotonic
        def average(seconds: float) -> float | None:
            values = [float(getattr(item, field)) for item in self.samples if now - item.monotonic <= seconds]
            return statistics.fmean(values) if values else None
        return MetricSummary(current, average(60.0), average(600.0))

    @property
    def collected_seconds(self) -> int:
        if len(self.samples) < 2:
            return 0
        return max(0, int(self.samples[-1].monotonic - self.samples[0].monotonic))
