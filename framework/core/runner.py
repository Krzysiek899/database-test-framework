"""
BenchmarkRunner – orchestrates the full benchmarking lifecycle.
"""

from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Dict, List, Optional, get_origin, get_args

from framework.core.config import load_config
from framework.core.registry import get_registry
from framework.drivers.base import DatabaseDriverInterface
from framework.drivers.factory import create_driver
from framework.infra.provider import InfraProvider
from framework.reporting.report import generate_report
from framework.telemetry.observer import Observer

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Top-level orchestrator."""

    def __init__(self, config_path: str = "config.yaml", suite_modules: Optional[List[str]] = None, indexed: bool = False, dataset_size: str = "small") -> None:
        self.cfg = load_config(config_path)
        self.global_cfg = self.cfg.get("global", {})
        self.results_dir = self.global_cfg.get("results_dir", "results")
        self.all_result_files: List[str] = []
        self.indexed = indexed
        self.dataset_size = dataset_size
        self.suite_modules = suite_modules or []

        # Import/reload suite modules to register decorators
        self._load_suites()

    def _load_suites(self) -> None:
        """Load/reload suite modules to register decorators from fresh environment."""
        # First, reload data.schema to ensure @Table decorators are re-registered
        if "data.schema" in sys.modules:
            del sys.modules["data.schema"]
        importlib.import_module("data.schema")
        logger.info("Loaded data schema")
        
        # Then reload suite modules
        for mod_name in self.suite_modules:
            # Remove from sys.modules and reimport to ensure fresh execution
            # This ensures @Table and @Benchmark decorators are re-evaluated
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            
            importlib.import_module(mod_name)
            logger.info("Loaded suite module: %s", mod_name)

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
                registry = get_registry()
                logger.debug("Registry tables: %s", [t.name for t in registry.tables])
                logger.debug("Registry setup: %s", registry.setup is not None)
                
                db = driver.get_db_interface() if hasattr(driver, "get_db_interface") else driver

                # Build schema from @Table metadata
                if hasattr(driver, "create_schema"):
                    table_defs = [self._build_table_def(table.name, table.model) for table in registry.tables]
                    logger.info("Creating %d tables: %s", len(table_defs), [t["name"] for t in table_defs])
                    driver.create_schema(table_defs)

                # Schema + seed - user defined now
                if registry.setup is not None:
                    registry.setup.fn(db)

                # Telemetry
                observer = Observer(
                    engine_name,
                    infra.get_container(),
                    stats_interval=self.global_cfg.get("stats_interval_sec", 0.5),
                    indexed=self.indexed,
                    dataset_size=self.dataset_size,
                )
                observer.start_resource_monitoring()

                # Execute benchmarks
                suites = registry.suites
                if not suites:
                    logger.warning("No @Suite functions registered!")

                for suite_meta in suites:
                    suite_instance = suite_meta.suite_cls()
                    for bench in suite_meta.benchmarks:
                        self._run_benchmark(db, observer, bench.name, getattr(suite_instance, bench.fn_name))

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
        db: Any,
        observer: Observer,
        test_name: str,
        func: Any,
    ) -> None:
        warmup = self.global_cfg.get("warmup_iterations", 3)
        iterations = self.global_cfg.get("benchmark_iterations", 10)

        logger.info("--- %s (warmup=%d, iter=%d, indexed=%s, size=%s) ---", 
                   test_name, warmup, iterations, self.indexed, self.dataset_size)

        # Warm-up
        for _ in range(warmup):
            func(db)

        # Collect engine metrics before
        driver = getattr(db, "driver", db)
        metrics_before = driver.get_metrics() if hasattr(driver, "get_metrics") else {}

        # Measured iterations
        for i in range(1, iterations + 1):
            observer.measure(
                test_name, i, func, db,
                indexed=self.indexed,
                dataset_size=self.dataset_size
            )
            logger.debug("  iteration %d/%d done", i, iterations)

        # Collect engine metrics after
        metrics_after = driver.get_metrics() if hasattr(driver, "get_metrics") else {}

        result = observer.create_result(test_name, iterations, metrics_before, metrics_after)
        avg_ms = (
            sum(t.duration_ms for t in result.timings) / len(result.timings)
            if result.timings
            else 0
        )
        logger.info("  avg = %.4f ms", avg_ms)

    @classmethod
    def _build_table_def(cls, table_name: str, model_cls: Any) -> Dict[str, Any]:
        columns = []
        relations = []
        model_fields = getattr(model_cls, "model_fields", {})
        for field_name, field_info in model_fields.items():
            ann = field_info.annotation
            origin = get_origin(ann)
            args = get_args(ann)

            # Support for nested models like List[Item]
            if origin is list and args and hasattr(args[0], "model_fields"):
                relations.append({
                    "name": field_name,
                    "type": "one_to_many",
                    "inner_model": args[0]
                })
            # Support for one-to-one nested BaseModel child
            elif hasattr(ann, "model_fields"):
                relations.append({
                    "name": field_name,
                    "type": "one_to_one",
                    "inner_model": ann
                })
            else:
                columns.append(
                    {
                        "name": field_name,
                        "python_type": getattr(ann, "__name__", str(ann)),
                        "nullable": not field_info.is_required(),
                        "primary_key": field_name == "id",
                    }
                )
        return {"name": table_name, "columns": columns, "relations": relations, "model": model_cls}

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
        elif engine_type == "mysql":
            params["user"] = env.get("MYSQL_USER", "bench")
            params["password"] = env.get("MYSQL_PASSWORD", "bench")
            params["dbname"] = env.get("MYSQL_DATABASE", "benchdb")
        elif engine_type == "couchdb":
            params["user"] = env.get("COUCHDB_USER", "bench")
            params["password"] = env.get("COUCHDB_PASSWORD", "bench")
        return params
