"""
Telemetry Observer – high-precision timing + Docker resource stats.

• Client-side: time.perf_counter_ns() around every measured call.
• Host-side: background thread streams ``docker stats`` via Docker API.
• Results are flushed to JSON (and optionally CSV) on demand.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import docker
from docker.models.containers import Container

logger = logging.getLogger(__name__)


# ---- data classes ---------------------------------------------------------

@dataclass
class TimingSample:
    """One measured execution of a benchmark function."""
    engine: str
    test_name: str
    iteration: int
    start_ns: int
    end_ns: int
    duration_ns: int
    duration_ms: float
    timestamp: str  # ISO-8601
    indexed: bool = False
    dataset_size: str = "medium"  # "small", "medium", "large"


@dataclass
class ResourceSample:
    """One snapshot of Docker container resource usage."""
    engine: str
    timestamp: str
    cpu_percent: float
    memory_bytes: int
    memory_limit_bytes: int
    memory_percent: float
    block_read_bytes: int
    block_write_bytes: int


@dataclass
class BenchmarkResult:
    """Aggregated result for a single test function across all iterations."""
    engine: str
    test_name: str
    iterations: int
    timings: List[TimingSample] = field(default_factory=list)
    resources: List[ResourceSample] = field(default_factory=list)
    engine_metrics_before: Dict[str, Any] = field(default_factory=dict)
    engine_metrics_after: Dict[str, Any] = field(default_factory=dict)


# ---- observer -------------------------------------------------------------

class Observer:
    """Captures timing + Docker stats for a benchmark session."""

    def __init__(
        self,
        engine_name: str,
        container: Container,
        stats_interval: float = 0.5,
    ) -> None:
        self.engine_name = engine_name
        self.container = container
        self.stats_interval = stats_interval

        self._resource_samples: List[ResourceSample] = []
        self._timing_samples: List[TimingSample] = []
        self._results: List[BenchmarkResult] = []

        self._stats_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Docker stats streaming (background thread)
    # ------------------------------------------------------------------
    def start_resource_monitoring(self) -> None:
        self._stop_event.clear()
        self._stats_thread = threading.Thread(
            target=self._stream_stats, daemon=True,
        )
        self._stats_thread.start()
        logger.debug("Resource monitoring started for %s", self.engine_name)

    def stop_resource_monitoring(self) -> None:
        self._stop_event.set()
        if self._stats_thread is not None:
            self._stats_thread.join(timeout=5)
        logger.debug("Resource monitoring stopped for %s", self.engine_name)

    def _stream_stats(self) -> None:
        try:
            for raw in self.container.stats(stream=True, decode=True):
                if self._stop_event.is_set():
                    break
                sample = self._parse_stats(raw)
                if sample is not None:
                    self._resource_samples.append(sample)
                time.sleep(self.stats_interval)
        except Exception as exc:
            logger.warning("Stats streaming error: %s", exc)

    def _parse_stats(self, raw: Dict[str, Any]) -> Optional[ResourceSample]:
        try:
            # CPU
            cpu_delta = (
                raw["cpu_stats"]["cpu_usage"]["total_usage"]
                - raw["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                raw["cpu_stats"]["system_cpu_usage"]
                - raw["precpu_stats"]["system_cpu_usage"]
            )
            online = raw["cpu_stats"].get("online_cpus", 1)
            cpu_pct = (cpu_delta / system_delta * online * 100.0) if system_delta > 0 else 0.0

            # Memory
            mem_usage = raw["memory_stats"].get("usage", 0)
            mem_limit = raw["memory_stats"].get("limit", 1)
            mem_pct = mem_usage / mem_limit * 100.0 if mem_limit else 0.0

            # Block I/O
            blk_read = blk_write = 0
            for entry in raw.get("blkio_stats", {}).get(
                "io_service_bytes_recursive", []
            ) or []:
                if entry["op"].lower() == "read":
                    blk_read += entry["value"]
                elif entry["op"].lower() == "write":
                    blk_write += entry["value"]

            return ResourceSample(
                engine=self.engine_name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cpu_percent=round(cpu_pct, 2),
                memory_bytes=mem_usage,
                memory_limit_bytes=mem_limit,
                memory_percent=round(mem_pct, 2),
                block_read_bytes=blk_read,
                block_write_bytes=blk_write,
            )
        except (KeyError, ZeroDivisionError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------
    def measure(
        self,
        test_name: str,
        iteration: int,
        func,
        *args,
        indexed: bool = False,
        dataset_size: str = "medium",
        **kwargs
    ) -> Any:
        """Call *func* and record a TimingSample. Returns func's result."""
        start = time.perf_counter_ns()
        result = func(*args, **kwargs)
        end = time.perf_counter_ns()
        duration_ns = end - start

        sample = TimingSample(
            engine=self.engine_name,
            test_name=test_name,
            iteration=iteration,
            start_ns=start,
            end_ns=end,
            duration_ns=duration_ns,
            duration_ms=round(duration_ns / 1_000_000, 4),
            timestamp=datetime.now(timezone.utc).isoformat(),
            indexed=indexed,
            dataset_size=dataset_size,
        )
        self._timing_samples.append(sample)
        return result

    # ------------------------------------------------------------------
    # Result aggregation
    # ------------------------------------------------------------------
    def create_result(
        self,
        test_name: str,
        iterations: int,
        engine_metrics_before: Dict[str, Any],
        engine_metrics_after: Dict[str, Any],
    ) -> BenchmarkResult:
        timings = [
            s for s in self._timing_samples if s.test_name == test_name
        ]
        result = BenchmarkResult(
            engine=self.engine_name,
            test_name=test_name,
            iterations=iterations,
            timings=timings,
            resources=list(self._resource_samples),
            engine_metrics_before=engine_metrics_before,
            engine_metrics_after=engine_metrics_after,
        )
        self._results.append(result)
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def flush_json(self, directory: str) -> str:
        """Write all collected results to a JSON file and return its path."""
        os.makedirs(directory, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(directory, f"{self.engine_name}_{ts}.json")
        payload = [asdict(r) for r in self._results]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        logger.info("Results written to %s", path)
        return path

    def flush_csv(self, directory: str) -> str:
        """Write timing samples to a flat CSV file."""
        os.makedirs(directory, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(directory, f"{self.engine_name}_{ts}_timings.csv")
        if not self._timing_samples:
            return path
        fieldnames = list(asdict(self._timing_samples[0]).keys())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for s in self._timing_samples:
                writer.writerow(asdict(s))
        logger.info("Timing CSV written to %s", path)
        return path

