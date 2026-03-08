"""
Report generator – reads per-engine JSON results and produces:
  • A combined comparative JSON file.
  • A bar-chart PNG comparing avg latencies per test across engines.
  • A summary printed to the console.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def generate_report(result_files: List[str], output_dir: str) -> None:
    """Load per-engine JSON results and produce a comparative report."""
    all_data: Dict[str, List[Dict[str, Any]]] = {}

    for path in result_files:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data:
            engine = entry["engine"]
            all_data.setdefault(engine, []).append(entry)

    # ---- comparative summary ----
    summary = _build_summary(all_data)
    _print_summary(summary)

    # ---- save comparative JSON ----
    os.makedirs(output_dir, exist_ok=True)
    summary_path = os.path.join(output_dir, "comparative_report.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    logger.info("Comparative JSON saved to %s", summary_path)

    # ---- generate chart ----
    try:
        _generate_chart(summary, output_dir)
    except Exception as exc:
        logger.warning("Chart generation failed (matplotlib may not be available): %s", exc)


# ---- internal helpers ----

def _build_summary(all_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Build a dict of {test_name: {engine: stats}}."""
    tests: Dict[str, Dict[str, Any]] = {}

    for engine, entries in all_data.items():
        for entry in entries:
            test_name = entry["test_name"]
            durations = [t["duration_ms"] for t in entry.get("timings", [])]
            if not durations:
                continue
            stats_dict = {
                "engine": engine,
                "iterations": len(durations),
                "avg_ms": round(statistics.mean(durations), 4),
                "median_ms": round(statistics.median(durations), 4),
                "min_ms": round(min(durations), 4),
                "max_ms": round(max(durations), 4),
                "stdev_ms": round(statistics.stdev(durations), 4) if len(durations) > 1 else 0.0,
            }
            tests.setdefault(test_name, {})[engine] = stats_dict

    return tests


def _print_summary(summary: Dict[str, Any]) -> None:
    header = f"{'Test':<35} {'Engine':<15} {'Avg (ms)':>10} {'Median':>10} {'Min':>10} {'Max':>10} {'Stdev':>10}"
    print("\n" + "=" * len(header))
    print("COMPARATIVE BENCHMARK REPORT")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for test_name, engines in summary.items():
        for engine, s in engines.items():
            print(
                f"{test_name:<35} {engine:<15} "
                f"{s['avg_ms']:>10.4f} {s['median_ms']:>10.4f} "
                f"{s['min_ms']:>10.4f} {s['max_ms']:>10.4f} "
                f"{s['stdev_ms']:>10.4f}"
            )
    print("=" * len(header) + "\n")


def _generate_chart(summary: Dict[str, Any], output_dir: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    test_names = list(summary.keys())
    if not test_names:
        return

    engines = sorted({e for tests in summary.values() for e in tests})
    x_pos = list(range(len(test_names)))
    bar_width = 0.8 / max(len(engines), 1)

    fig, ax = plt.subplots(figsize=(max(10, len(test_names) * 2), 6))
    for i, engine in enumerate(engines):
        avgs = [
            summary[t].get(engine, {}).get("avg_ms", 0) for t in test_names
        ]
        positions = [x + i * bar_width for x in x_pos]
        ax.bar(positions, avgs, bar_width, label=engine)

    ax.set_xlabel("Test")
    ax.set_ylabel("Average Latency (ms)")
    ax.set_title("Benchmark Comparison")
    ax.set_xticks([x + bar_width * (len(engines) - 1) / 2 for x in x_pos])
    ax.set_xticklabels(test_names, rotation=30, ha="right")
    ax.legend()
    fig.tight_layout()

    chart_path = os.path.join(output_dir, "benchmark_comparison.png")
    fig.savefig(chart_path, dpi=150)
    plt.close(fig)
    logger.info("Chart saved to %s", chart_path)

