#!/usr/bin/env python3
"""
run_benchmarks.py – CLI entry point for the Database Benchmarking Framework.

Usage:
    python run_benchmarks.py                        # run all engines
    python run_benchmarks.py --engines postgres      # run only postgres
    python run_benchmarks.py --config my_config.yaml # custom config
    python run_benchmarks.py --suite suites.my_suite  # custom suite module

Workflow:
  For each dataset size (small, medium, large):
    For each indexing mode (without_index, with_index):
      Run benchmarks for all engines
  Generate comprehensive reports and visualizations
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from framework.core.runner import BenchmarkRunner
from framework.core.registry import clear_registry
from framework.reporting.visualizations import generate_all_visualizations
from framework.reporting.html_generator import HTMLReportGenerator


logger = logging.getLogger(__name__)


DATASET_SIZES = ["small", "medium", "large"]
INDEXING_MODES = [False, True]  # False = without index, True = with index


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def run_orchestrator(
    config_path: str = "config.yaml",
    suite_modules: list = None,
    engines: list = None,
    log_level: str = "INFO",
) -> None:
    """Run benchmarks for all dataset sizes and indexing modes."""
    setup_logging(log_level)
    logger.info("=" * 70)
    logger.info("DATABASE BENCHMARK ORCHESTRATOR")
    logger.info("=" * 70)

    suite_modules = suite_modules or ["suites.online_learning_platform_suite"]
    engines = engines or ["postgres", "mongodb", "mysql"]

    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    logger.info("Results directory: %s", results_dir.absolute())

    all_result_files = []

    # Outer loop: dataset sizes
    for dataset_size in DATASET_SIZES:
        logger.info("\n" + "=" * 70)
        logger.info("DATASET SIZE: %s", dataset_size.upper())
        logger.info("=" * 70)

        # Set environment variable for suite module
        os.environ["DATASET_SIZE"] = dataset_size

        # Inner loop: indexing modes
        for indexed in INDEXING_MODES:
            index_label = "WITH INDEXES" if indexed else "WITHOUT INDEXES"
            logger.info("\n" + "-" * 70)
            logger.info("Indexing Mode: %s", index_label)
            logger.info("-" * 70)

            engines_to_run = engines
            if indexed:
                engines_to_run = [e for e in engines if e not in ["couchdb"]]
                if not engines_to_run:
                    logger.info("Skipped: CouchDB do not support indexing yet")
                    continue

            try:
                # Reset registry state before reimporting suites and schemas
                from framework.core.registry import clear_registry
                clear_registry()

                # Set environment variable for indexing mode
                os.environ["INDEXED_MODE"] = "true" if indexed else "false"

                # Create runner with current parameters
                # (this will reload/reimport suite modules and schema with fresh registry)
                runner = BenchmarkRunner(
                    config_path=config_path,
                    suite_modules=suite_modules,
                    indexed=indexed,
                    dataset_size=dataset_size,
                )

                # Run benchmarks
                runner.run(engines=engines_to_run)

                # Collect result files
                all_result_files.extend(runner.all_result_files)

                logger.info("Completed: %s dataset, %s indexing", dataset_size, index_label)

            except Exception as exc:
                logger.error("Failed: %s dataset, %s indexing: %s",
                           dataset_size, index_label, exc)
                raise

    logger.info("\n" + "=" * 70)
    logger.info("GENERATING VISUALIZATIONS")
    logger.info("=" * 70)

    # Generate comprehensive visualizations
    try:
        generate_all_visualizations(all_result_files, str(results_dir))
        logger.info("Visualizations generated successfully")
    except Exception as exc:
        logger.error("Visualization generation failed: %s", exc)
        raise
# Generate HTML report
    try:
        html_gen = HTMLReportGenerator(results_dir=str(results_dir))
        html_gen.generate()
    except Exception as exc:
        logger.error("HTML report generation failed: %s", exc)
        raise

    
    logger.info("\n" + "=" * 70)
    logger.info("ORCHESTRATION COMPLETE")
    logger.info("Results saved to: %s", results_dir.absolute())
    logger.info("=" * 70)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Orchestrate database benchmarks across dataset sizes and indexing modes",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--engines",
        nargs="*",
        default=["postgres", "mysql", "mongodb", "couchdb"],
        help="Engine names to benchmark (default: postgres, mysql, mongodb, couchdb)",
    )
    parser.add_argument(
        "--suite",
        nargs="*",
        default=["suites.online_learning_platform_suite"],
        help="Python module paths containing @benchmark functions",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    run_orchestrator(
        config_path=args.config,
        suite_modules=args.suite,
        engines=args.engines,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

