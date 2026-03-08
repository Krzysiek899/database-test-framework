#!/usr/bin/env python3
"""
run_benchmarks.py – CLI entry point for the Database Benchmarking Framework.

Usage:
    python run_benchmarks.py                        # run all engines
    python run_benchmarks.py --engines postgres      # run only postgres
    python run_benchmarks.py --config my_config.yaml # custom config
    python run_benchmarks.py --suite suites.my_suite  # custom suite module
"""

from __future__ import annotations

import argparse
import logging
import sys

from framework.core.runner import BenchmarkRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Database Benchmarking Framework",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--engines",
        nargs="*",
        default=None,
        help="Engine names to benchmark (default: all defined in config)",
    )
    parser.add_argument(
        "--suite",
        nargs="*",
        default=["suites.example_suite"],
        help="Python module paths containing @benchmark functions",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    runner = BenchmarkRunner(
        config_path=args.config,
        suite_modules=args.suite,
    )
    runner.run(engines=args.engines)


if __name__ == "__main__":
    main()

