#!/usr/bin/env python3
"""
Standalone script to generate HTML report from existing benchmark results.

Usage:
    python generate_report.py [--results-dir RESULTS_DIR] [--output-dir OUTPUT_DIR]

This script generates an HTML report from benchmark results stored in the
results directory. It does NOT run benchmarks – it only generates visualizations
from existing results in summary_metrics.csv and results/charts/*.png.

If you haven't run benchmarks yet, execute:
    python run_benchmarks.py
"""

import argparse
import logging
import sys
from pathlib import Path

from framework.reporting.html_generator import HTMLReportGenerator


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def main() -> None:
    """CLI entry point for HTML report generation."""
    parser = argparse.ArgumentParser(
        description="Generate static HTML report from benchmark results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_report.py
    → Generate report from ./results, save to ./results/report.html
    
  python generate_report.py --results-dir /path/to/results
    → Generate report from custom results directory
    
  python generate_report.py --results-dir ./results --log-level DEBUG
    → Generate with debug logging
        """,
    )
    
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Path to benchmark results directory (default: results/)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    
    args = parser.parse_args()
    
    setup_logging(args.log_level)
    
    # Validate results directory
    results_path = Path(args.results_dir)
    if not results_path.exists():
        print(f"✗ Error: Results directory not found: {results_path.absolute()}")
        print("  Please run benchmarks first: python run_benchmarks.py")
        sys.exit(1)
    
    summary_csv = results_path / "summary_metrics.csv"
    if not summary_csv.exists():
        print(f"✗ Error: summary_metrics.csv not found in {results_path.absolute()}")
        print("  Please run benchmarks first: python run_benchmarks.py")
        sys.exit(1)
    
    # Generate report
    try:
        logger = logging.getLogger(__name__)
        logger.info("=" * 70)
        logger.info("STANDALONE HTML REPORT GENERATOR")
        logger.info("=" * 70)
        
        html_gen = HTMLReportGenerator(results_dir=str(results_path))
        html_gen.generate()
        
        logger.info("\n" + "=" * 70)
        logger.info("✓ Report generation complete")
        logger.info("=" * 70)
        
    except Exception as exc:
        print(f"✗ Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
