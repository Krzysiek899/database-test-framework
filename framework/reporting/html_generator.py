"""
HTML Report Generator – creates static HTML reports from benchmark results.

Reads from:
  • summary_metrics.csv (aggregated benchmark statistics)
  • results/charts/*.png (benchmark visualization charts)

Generates:
  • results/report.html (single static HTML file with embedded CSS, no external dependencies)
"""

from __future__ import annotations

import csv
import glob
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HTMLReportGenerator:
    """Generate static HTML reports from benchmark results."""

    def __init__(self, results_dir: str = "results") -> None:
        """
        Initialize HTML report generator.

        Args:
            results_dir: Path to directory containing benchmark results (default: "results")
        """
        self.results_dir = Path(results_dir)
        self.charts_dir = self.results_dir / "charts"
        self.summary_csv = self.results_dir / "summary_metrics.csv"
        
        self.results: List[Dict[str, Any]] = []
        self.chart_files: List[str] = []
        self.generation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate(self) -> None:
        """Generate HTML report from available results."""
        logger.info("=" * 70)
        logger.info("HTML REPORT GENERATOR")
        logger.info("=" * 70)
        
        if not self.summary_csv.exists():
            logger.error("summary_metrics.csv not found at %s", self.summary_csv)
            logger.error("  Please run benchmarks first: python run_benchmarks.py")
            return
        
        logger.info("Loading results from %s", self.summary_csv)
        self._load_results()
        
        logger.info("Loading chart images from %s", self.charts_dir)
        self._load_charts()
        
        if not self.results:
            logger.error("No results found in summary_metrics.csv")
            return
        
        logger.info("Generating HTML report...")
        html_content = self._build_html()
        
        output_path = self.results_dir / "report.html"
        output_path.write_text(html_content, encoding="utf-8")
        
        logger.info("HTML report generated: %s", output_path.absolute())
        logger.info("Open in browser: file://%s", output_path.absolute())

    def _load_results(self) -> None:
        """Load results from summary_metrics.csv."""
        if not self.summary_csv.exists():
            logger.warning("summary_metrics.csv not found")
            return
        
        try:
            with open(self.summary_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert string values to appropriate types
                    result = {
                        "engine": row["engine"],
                        "test_name": row["test_name"],
                        "indexed": row["indexed"].lower() == "true",
                        "dataset_size": row["dataset_size"],
                        "avg_ms": float(row["avg_ms"]),
                        "median_ms": float(row["median_ms"]),
                        "min_ms": float(row["min_ms"]),
                        "max_ms": float(row["max_ms"]),
                        "stdev_ms": float(row["stdev_ms"]),
                        "samples": int(row["samples"]),
                    }
                    self.results.append(result)
            
            logger.info("Loaded %d result rows from summary_metrics.csv", len(self.results))
        except Exception as exc:
            logger.error("Failed to load summary_metrics.csv: %s", exc)
            raise

    def _load_charts(self) -> None:
        """Load PNG chart filenames from results/charts directory."""
        if not self.charts_dir.exists():
            logger.warning("charts directory not found at %s", self.charts_dir)
            return
        
        png_files = sorted(glob.glob(str(self.charts_dir / "*.png")))
        self.chart_files = [Path(f).name for f in png_files]
        
        logger.info("Found %d chart images", len(self.chart_files))
        if len(self.chart_files) < 16:
            logger.warning(
                "Expected 16 chart images, found %d. Some visualizations may be missing.",
                len(self.chart_files)
            )

    def _build_html(self) -> str:
        """Build complete HTML report."""
        parts = [
            self._render_html_header(),
            self._render_page_title(),
            self._render_charts_section(),
            self._render_summary_table(),
            self._render_detailed_tables(),
            self._render_html_footer(),
        ]
        return "\n".join(parts)

    def _render_html_header(self) -> str:
        """Render HTML header with meta tags, title, and embedded CSS."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Database Benchmark Report</title>
    <style>
{self._render_css()}
    </style>
</head>
<body>
"""

    def _render_html_footer(self) -> str:
        """Render HTML footer."""
        return """</body>
</html>
"""

    def _render_css(self) -> str:
        """Render embedded CSS styles."""
        return """        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background-color: #2c3e50;
            color: white;
            padding: 40px 20px;
            margin-bottom: 30px;
            border-radius: 4px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header .metadata {
            font-size: 0.95em;
            opacity: 0.85;
        }
        
        .section {
            background-color: white;
            margin-bottom: 30px;
            padding: 25px;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        
        .section h2 {
            font-size: 1.8em;
            margin-bottom: 20px;
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }
        
        .section h3 {
            font-size: 1.3em;
            margin-top: 25px;
            margin-bottom: 15px;
            color: #34495e;
        }
        
        .charts-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
            margin-top: 20px;
        }
        
        .chart-item {
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            border: 1px solid #e0e0e0;
        }
        
        .chart-item img {
            width: 100%;
            height: auto;
            display: block;
            border-radius: 2px;
        }
        
        .chart-item .chart-title {
            font-size: 0.95em;
            font-weight: 600;
            color: #555;
            margin-top: 10px;
            text-align: center;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            background-color: white;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        }
        
        table th {
            background-color: white;
            color: #333;
            padding: 8px 10px;
            text-align: left;
            font-weight: 600;
            border: 1px solid #ddd;
        }
        
        table td {
            padding: 8px 10px;
            border: 1px solid #ddd;
            background-color: white;
        }
        
        table tbody tr:nth-child(even) {
            background-color: white;
        }
        
        table tbody tr:hover {
            background-color: white;
        }
        
        .metric-value {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            font-weight: 500;
            text-align: right;
        }
        
        .comparison-table-group table {
            font-size: 0.85em;
        }
        
        .comparison-table-group table th,
        .comparison-table-group table td {
            padding: 6px 8px;
        }
        
        .engine-column {
            font-weight: 600;
            color: #2980b9;
        }
        
        .test-column {
            font-weight: 500;
        }
        
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }
        
        .badge-indexed {
            background-color: #d4edda;
            color: #155724;
        }
        
        .badge-unindexed {
            background-color: #f8d7da;
            color: #721c24;
        }
        
        .badge-small {
            background-color: #cfe2ff;
            color: #084298;
        }
        
        .badge-medium {
            background-color: #e7d4f5;
            color: #5a3e8f;
        }
        
        .badge-large {
            background-color: #ffecb5;
            color: #b8860b;
        }
        
        .comparison-table-group {
            margin-bottom: 30px;
        }
        
        @media (max-width: 1024px) {
            .charts-grid {
                grid-template-columns: 1fr;
            }
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .header {
                padding: 20px;
            }
            
            .header h1 {
                font-size: 1.8em;
            }
            
            .section {
                padding: 15px;
            }
            
            table {
                font-size: 0.9em;
            }
            
            table th, table td {
                padding: 8px 10px;
            }
        }
"""

    def _render_page_title(self) -> str:
        """Render page title and metadata section."""
        test_count = len(set(r["test_name"] for r in self.results))
        engine_count = len(set(r["engine"] for r in self.results))
        
        return f"""<div class="container">
    <div class="header">
        <h1>Database Benchmark Report</h1>
        <div class="metadata">
            <p>Generated: {self.generation_time}</p>
            <p>Tests: {test_count} | Engines: {engine_count} | Total Measurements: {len(self.results)}</p>
        </div>
    </div>
</div>
"""

    def _render_charts_section(self) -> str:
        """Render section with benchmark charts in single column."""
        if not self.chart_files:
            return '<div class="container"><div class="section"><p>No charts available</p></div></div>'
        
        chart_html = '<div class="container"><div class="section"><h2>Benchmark Visualizations</h2><div class="charts-grid">'
        
        for chart_file in self.chart_files:
            # Extract test name from filename (remove .png)
            test_name = chart_file.replace(".png", "")
            # Format test name for display (replace underscores with spaces, title case)
            display_name = test_name.replace("_", " ").title()
            
            chart_path = f"charts/{chart_file}"
            chart_html += f"""
        <div class="chart-item">
            <img src="{chart_path}" alt="{display_name}" loading="lazy">
            <div class="chart-title">{display_name}</div>
        </div>
"""
        
        chart_html += """    </div></div></div>
"""
        return chart_html

    def _render_summary_table(self) -> str:
        """Render summary tables per test."""
        # Define engine sort order: postgres, postgres indexed, mysql, mysql indexed, mongo, mongo indexed, couch, couch indexed
        engine_order = {
            ("postgres", False): 0,
            ("postgres", True): 1,
            ("mysql", False): 2,
            ("mysql", True): 3,
            ("mongodb", False): 4,
            ("mongodb", True): 5,
            ("couchdb", False): 6,
            ("couchdb", True): 7,
        }
        
        # Group results by test_name
        tests_dict: Dict[str, List[Dict[str, Any]]] = {}
        
        for result in self.results:
            test_name = result["test_name"]
            if test_name not in tests_dict:
                tests_dict[test_name] = []
            tests_dict[test_name].append(result)
        
        # Sort tests
        sorted_tests = sorted(tests_dict.items())
        
        table_html = """<div class="container">
    <div class="section">
        <h2>Summary Results</h2>
        <p style="margin-bottom: 20px; color: #666; font-size: 0.95em;">
            All benchmark measurements aggregated per engine and dataset configuration.
        </p>
"""
        
        for test_name, test_results in sorted_tests:
            table_html += f"""        <div class="comparison-table-group">
            <h3>{test_name}</h3>
            <table>
                <thead>
                    <tr>
                        <th>Engine</th>
                        <th>Indexed</th>
                        <th>Dataset Size</th>
                        <th class="metric-value">Avg (ms)</th>
                        <th class="metric-value">Median (ms)</th>
                        <th class="metric-value">Min (ms)</th>
                        <th class="metric-value">Max (ms)</th>
                        <th class="metric-value">Stdev (ms)</th>
                        <th class="metric-value">Samples</th>
                    </tr>
                </thead>
                <tbody>
"""
            
            # Sort results: first by dataset size, then by engine order (postgres, mysql, mongodb, couchdb with indexed variations)
            sorted_results = sorted(
                test_results,
                key=lambda x: (
                    x["dataset_size"],
                    engine_order.get((x["engine"], x["indexed"]), 999)
                )
            )
            
            for result in sorted_results:
                indexed_label = "Yes" if result["indexed"] else "No"
                
                table_html += f"""                    <tr>
                        <td>{result['engine']}</td>
                        <td>{indexed_label}</td>
                        <td>{result['dataset_size'].upper()}</td>
                        <td class="metric-value">{result['avg_ms']:.4f}</td>
                        <td class="metric-value">{result['median_ms']:.4f}</td>
                        <td class="metric-value">{result['min_ms']:.4f}</td>
                        <td class="metric-value">{result['max_ms']:.4f}</td>
                        <td class="metric-value">{result['stdev_ms']:.4f}</td>
                        <td class="metric-value">{result['samples']}</td>
                    </tr>
"""
            
            table_html += """                </tbody>
            </table>
        </div>
"""
        
        table_html += """    </div>
</div>
"""
        return table_html

    def _render_detailed_tables(self) -> str:
        """Render detailed comparison tables per test."""
        # Define engine sort order: postgres, postgres indexed, mysql, mysql indexed, mongo, mongo indexed, couch, couch indexed
        engine_order = {
            ("postgres", False): 0,
            ("postgres", True): 1,
            ("mysql", False): 2,
            ("mysql", True): 3,
            ("mongodb", False): 4,
            ("mongodb", True): 5,
            ("couchdb", False): 6,
            ("couchdb", True): 7,
        }
        
        # Group results by test_name
        tests_dict: Dict[str, List[Dict[str, Any]]] = {}
        
        for result in self.results:
            test_name = result["test_name"]
            if test_name not in tests_dict:
                tests_dict[test_name] = []
            tests_dict[test_name].append(result)
        
        # Sort tests
        sorted_tests = sorted(tests_dict.items())
        
        tables_html = """<div class="container">
    <div class="section">
        <h2>Detailed Comparison Tables</h2>
        <p style="margin-bottom: 20px; color: #666; font-size: 0.95em;">
            Performance comparison across all engines for each test.
        </p>
"""
        
        for test_name, test_results in sorted_tests:
            tables_html += f"""        <div class="comparison-table-group">
            <h3>{test_name}</h3>
            <table>
                <thead>
                    <tr>
                        <th>Dataset Size / Indexing</th>
"""
            
            # Get unique engines and sort by preferred order
            unique_engines_set = set(r["engine"] for r in test_results)
            engines = sorted(unique_engines_set, key=lambda e: engine_order.get((e, False), 999))
            
            for engine in engines:
                tables_html += f"                        <th colspan=\"5\" style=\"text-align: center;\"><strong>{engine}</strong></th>\n"
            
            tables_html += """                    </tr>
                    <tr>
                        <th></th>
"""
            
            for engine in engines:
                tables_html += f"""                        <th class="metric-value">Avg</th>
                        <th class="metric-value">Med</th>
                        <th class="metric-value">Min</th>
                        <th class="metric-value">Max</th>
                        <th class="metric-value">Stdev</th>
"""
            
            tables_html += """                    </tr>
                </thead>
                <tbody>
"""
            
            # Get unique dataset/indexing combinations and sort them
            configs = sorted(set((r["dataset_size"], r["indexed"]) for r in test_results),
                           key=lambda x: (x[0], x[1]))
            
            for dataset_size, indexed in configs:
                indexed_label = "indexed" if indexed else "unindexed"
                tables_html += f'                    <tr><td class="test-column"><strong>{dataset_size.upper()} ({indexed_label})</strong></td>'
                
                for engine in engines:
                    # Find result for this engine + dataset + indexed combination
                    result = next(
                        (r for r in test_results 
                         if r["engine"] == engine and r["dataset_size"] == dataset_size and r["indexed"] == indexed),
                        None
                    )
                    
                    if result:
                        tables_html += f"""<td class="metric-value">{result['avg_ms']:.4f}</td>
                    <td class="metric-value">{result['median_ms']:.4f}</td>
                    <td class="metric-value">{result['min_ms']:.4f}</td>
                    <td class="metric-value">{result['max_ms']:.4f}</td>
                    <td class="metric-value">{result['stdev_ms']:.4f}</td>
"""
                    else:
                        tables_html += """<td class="metric-value">—</td>
                    <td class="metric-value">—</td>
                    <td class="metric-value">—</td>
                    <td class="metric-value">—</td>
                    <td class="metric-value">—</td>
"""
                
                tables_html += "</tr>\n"
            
            tables_html += """                </tbody>
            </table>
        </div>
"""
        
        tables_html += """    </div>
</div>
"""
        return tables_html
