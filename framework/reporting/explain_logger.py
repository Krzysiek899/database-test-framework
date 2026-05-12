"""
ExplainLogger – centralises EXPLAIN query logging across all database drivers.

Each unique (context, table_name, filter) triple is logged exactly once per
driver session, preventing duplicate entries when a benchmark iterates the same
query multiple times (warmup + measured iterations).
"""

from __future__ import annotations

import os
from typing import Any, Optional


class ExplainLogger:
    """Collects and writes EXPLAIN output, deduplicating per session."""

    def __init__(self, db_label: str, run_timestamp: str, results_dir: str = "results"):
        self._db_label = db_label
        self._run_timestamp = run_timestamp
        self._results_dir = results_dir
        self._seen: set[tuple] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        explain_lines: list[str],
        table_name: str,
        filter_repr: Any,
        query: Optional[str] = None,
        context: Optional[str] = None,
    ) -> bool:
        """Write an EXPLAIN result to the log file if not already seen."""
        dedup_key = (context, table_name, str(filter_repr))
        if dedup_key in self._seen:
            return False
        self._seen.add(dedup_key)

        log_dir = os.path.join(self._results_dir, "explain_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{self._db_label}_{self._run_timestamp}.txt")

        with open(log_path, "a", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            if context:
                f.write(f"BENCHMARK : {context}\n")
            f.write(f"TABLE     : {table_name}\n")
            f.write(f"FILTER    : {filter_repr}\n")
            if query:
                f.write(f"QUERY     : {query}\n")
            f.write("-" * 70 + "\n")
            for line in explain_lines:
                f.write(f"{line}\n")
            f.write("\n")

        return True

    def reset(self) -> None:
        """Clear the deduplication cache (call between independent test runs if needed)."""
        self._seen.clear()

