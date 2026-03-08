"""
BenchmarkRunner – orchestrates the full benchmarking lifecycle.

Workflow:
  1. Read config → identify target engines.
  2. For each engine:
     a. Spin up container (InfraProvider).
     b. Create driver & connect (DriverFactory).
     c. Apply schema + seed data (DataOrchestrator).
     d. For each registered @benchmark test:
        i.   Warm-up (non-measured iterations).
        ii.  Benchmark (measured iterations with telemetry).
     e. Flush results (JSON + CSV).
     f. Teardown container.
  3. Generate comparative report.
"""

from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Dict, List, Optional

from framework.core.config import load_config
from framework.core.decorators import get_registered_benchmarks
from framework.data.orchestrator import DataOrchestrator
from framework.drivers.factory import create_driver
from framework.drivers.base import DatabaseDriverInterface
from framework.infra.provider import InfraProvider
from framework.telemetry.observer import Observer
from framework.reporting.report import generate_report

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Top-level orchestrator."""

    def __init__(self, config_path: str = "config.yaml", suite_modules: Optional[List[str]] = None) -> None:
        self.cfg = load_config(config_path)
        self.global_cfg = self.cfg.get("global", {})
        self.results_dir = self.global_cfg.get("results_dir", "results")
        self.all_result_files: List[str] = []

        # Import suite modules so that @benchmark decorators fire
        for mod_name in (suite_modules or []):
            if mod_name not in sys.modules:
                importlib.import_module(mod_name)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def run(self, engines: Optional[List[str]] = None) -> None:
        """Run benchmarks against selected (or all) engines."""
        target_engines = engines or list(self.cfg["engines"].keys())
        logger.info("Target engines: %s", target_engines)

        try:
            for engine_name in target_engines:
                engine_cfg = self.cfg["engines"][engine_name]
                logger.info("=" * 60)
                logger.info("Engine: %s (%s)", engine_name, engine_cfg["image"])
                logger.info("=" * 60)
                self._run_engine(engine_name, engine_cfg)
        except RuntimeError as exc:
            # Covers Docker-not-running and other infrastructure errors
            logger.error("%s", exc)
            raise SystemExit(1) from None

        # Comparative report
        if self.all_result_files:
            generate_report(self.all_result_files, self.results_dir)

    # ------------------------------------------------------------------
    # Per-engine workflow
    # ------------------------------------------------------------------
    def _run_engine(self, engine_name: str, engine_cfg: Dict[str, Any]) -> None:
        infra = InfraProvider(engine_name, engine_cfg)
        with infra:
            # Build connection params from engine config
            conn_params = self._build_conn_params(engine_cfg)
            driver = create_driver(engine_name, engine_cfg["engine_type"], conn_params)
            driver.connect()

            try:
                # Schema + seed
                schema_cfg = self.cfg.get("schema", {})
                seeding_cfg = self.cfg.get("seeding", {})
                seed = self.global_cfg.get("seed", 42)
                orchestrator = DataOrchestrator(driver, engine_cfg["engine_type"], schema_cfg, seeding_cfg, seed)
                orchestrator.setup()

                # Telemetry
                observer = Observer(
                    engine_name,
                    infra.get_container(),
                    stats_interval=self.global_cfg.get("stats_interval_sec", 0.5),
                )
                observer.start_resource_monitoring()

                # Execute benchmarks
                benchmarks = get_registered_benchmarks()
                if not benchmarks:
                    logger.warning("No @benchmark functions registered!")

                for entry in benchmarks:
                    self._run_benchmark(driver, observer, entry)

                observer.stop_resource_monitoring()

                # Flush results
                json_path = observer.flush_json(self.results_dir)
                observer.flush_csv(self.results_dir)
                self.all_result_files.append(json_path)

            finally:
                driver.disconnect()

    # ------------------------------------------------------------------
    # Benchmark execution
    # ------------------------------------------------------------------
    def _run_benchmark(
        self,
        driver: DatabaseDriverInterface,
        observer: Observer,
        entry: Dict[str, Any],
    ) -> None:
        test_name = entry["name"]
        func = entry["func"]
        warmup = entry.get("warmup") or self.global_cfg.get("warmup_iterations", 3)
        iterations = entry.get("iterations") or self.global_cfg.get("benchmark_iterations", 10)

        logger.info("--- %s (warmup=%d, iter=%d) ---", test_name, warmup, iterations)

        # Warm-up
        for _ in range(warmup):
            func(driver)

        # Collect engine metrics before
        metrics_before = driver.get_metrics()

        # Measured iterations
        for i in range(1, iterations + 1):
            observer.measure(test_name, i, func, driver)
            logger.debug("  iteration %d/%d done", i, iterations)

        # Collect engine metrics after
        metrics_after = driver.get_metrics()

        result = observer.create_result(test_name, iterations, metrics_before, metrics_after)
        avg_ms = (
            sum(t.duration_ms for t in result.timings) / len(result.timings)
            if result.timings
            else 0
        )
        logger.info("  avg = %.4f ms", avg_ms)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_conn_params(engine_cfg: Dict[str, Any]) -> Dict[str, Any]:
        env = engine_cfg.get("environment", {})
        engine_type = engine_cfg["engine_type"]
        params: Dict[str, Any] = {
            "host": "127.0.0.1",
            "port": engine_cfg["host_port"],
        }
        if engine_type == "postgres":
            params["user"] = env.get("POSTGRES_USER", "bench")
            params["password"] = env.get("POSTGRES_PASSWORD", "bench")
            params["dbname"] = env.get("POSTGRES_DB", "benchdb")
        elif engine_type == "mongodb":
            params["user"] = env.get("MONGO_INITDB_ROOT_USERNAME", "bench")
            params["password"] = env.get("MONGO_INITDB_ROOT_PASSWORD", "bench")
            params["dbname"] = env.get("MONGO_INITDB_DATABASE", "benchdb")
        return params

