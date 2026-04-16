"""
Per-test benchmark visualizations.

Generates:
- One bar chart per test showing performance across all engines
- Grouped by dataset size and indexed/non-indexed variants
- Summary metrics (CSV/Markdown tables)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

logger = logging.getLogger(__name__)

# Fixed colors per engine (consistent across all charts)
ENGINE_COLORS = {
    "postgres": "#1f77b4",           # blue unindexed
    "postgres_indexed": "#6bb1e3",  # darker blue indexed
    "mysql": "#d62728",              # red unindexed
    "mysql_indexed": "#ed7474",      # darker red indexed
    "mongodb": "#ff7f0e",            # orange unindexed
    "mongodb_indexed": "#f5b57d",    # darker orange indexed
    "couchdb": "#2ca02c",            # green unindexed
    "couchdb_indexed": "#91cb8a",    # darker green indexed
}

# Map dataset size labels to actual row counts
DATASET_SIZE_MAPPING = {
    "small": 50,
    "medium": 100,
    "large": 200,
}


class BenchmarkVisualizer:
    """Generate per-test chart visualizations from benchmark results."""

    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        self.charts_dir = self.results_dir / "charts"
        self.charts_dir.mkdir(exist_ok=True)
        self.data = []
        self.df = None

    def load_results(self, result_files: List[str]) -> None:
        """Load all benchmark result JSON files and create DataFrame."""
        logger.info("Loading %d result files...", len(result_files))

        for filepath in result_files:
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    results = json.load(fh)
                    for result in results:
                        for timing in result.get("timings", []):
                            self.data.append({
                                "engine": timing["engine"],
                                "test_name": timing["test_name"],
                                "iteration": timing["iteration"],
                                "duration_ms": timing["duration_ms"],
                                "indexed": timing.get("indexed", False),
                                "dataset_size": timing.get("dataset_size", "medium"),
                                "timestamp": timing["timestamp"],
                            })
            except Exception as exc:
                logger.warning("Failed to load %s: %s", filepath, exc)

        if not self.data:
            logger.warning("No timing data loaded!")
            return

        self.df = pd.DataFrame(self.data)
        logger.info("Loaded %d timing samples", len(self.df))



    def generate_per_test_charts(self) -> None:
        """Generate one bar chart per test showing performance across all engines and data sizes."""
        if self.df is None or self.df.empty:
            logger.warning("No data to generate per-test charts")
            return
        
        test_names = sorted(self.df["test_name"].unique())
        logger.info("Generating %d per-test charts...", len(test_names))
        
        for test_name in test_names:
            logger.info("  → %s", test_name)
            test_data = self.df[self.df["test_name"] == test_name].copy()
            
            if test_data.empty:
                logger.warning("    ⊘ No data for test %s", test_name)
                continue
            
            # Get aggregated data
            agg_data = (
                test_data.groupby(["dataset_size", "engine", "indexed"])["duration_ms"]
                .mean()
                .reset_index()
            )
            
            # Create Plotly figure
            fig = go.Figure()
            
            # Get unique dataset sizes and engines for grouping
            # Sort dataset sizes by actual row count, not alphabetically
            unique_sizes = agg_data["dataset_size"].unique()
            dataset_sizes = sorted(unique_sizes, key=lambda x: DATASET_SIZE_MAPPING.get(x, 0))
            engines = sorted(agg_data["engine"].unique())
            
            # Calculate x-axis positions dynamically based on actual data
            # (this handles cases where some engine/indexed combinations don't exist)
            bar_width = 0.25
            gap_between_bars = 0.03  # gap between bars
            gap_between_groups = 1.2   # gap between dataset size groups
            
            x_position_map = {}  # (size, engine, indexed) -> x_pos
            x_group_centers = {}  # size -> x_center for tick labels
            x_counter = 0
            
            for size_idx, size in enumerate(dataset_sizes):
                group_start_x = x_counter
                size_data = agg_data[agg_data["dataset_size"] == size]
                
                # Get all (engine, indexed) combinations that exist for this size
                existing_combinations = sorted(
                    size_data[["engine", "indexed"]].drop_duplicates().values.tolist(),
                    key=lambda x: (x[0], x[1])  # sort by engine name, then indexed
                )
                
                # Distribute bars evenly for this size group
                for combo_idx, (engine, indexed) in enumerate(existing_combinations):
                    x_pos = x_counter
                    x_position_map[(size, engine, indexed)] = x_pos
                    x_counter += bar_width + gap_between_bars
                
                # Remove last gap and record group center for x-axis tick
                x_counter -= gap_between_bars
                group_end_x = x_counter
                x_group_centers[size] = (group_start_x + group_end_x) / 2
                
                # Gap between groups
                x_counter += gap_between_groups
            
            # Create traces for each (engine, indexed) combination that exists in data
            all_combinations = sorted(
                agg_data[["engine", "indexed"]].drop_duplicates().values.tolist(),
                key=lambda x: (x[0], x[1])  # sort by engine name, then indexed
            )
            
            for engine, indexed in all_combinations:
                engine_indexed_data = agg_data[(agg_data["engine"] == engine) & (agg_data["indexed"] == indexed)]
                engine_indexed_data = engine_indexed_data.sort_values("dataset_size")
                
                x_vals = []
                y_vals = []
                
                for size in dataset_sizes:
                    matching = engine_indexed_data[engine_indexed_data["dataset_size"] == size]
                    if not matching.empty:
                        x_vals.append(x_position_map[(size, engine, indexed)])
                        y_vals.append(matching["duration_ms"].values[0])
                
                # Determine label
                label = f"{engine} (indexed)" if indexed else f"{engine}"
                color_key = f"{engine}_indexed" if indexed else engine
                
                fig.add_trace(go.Bar(
                    x=x_vals,
                    y=y_vals,
                    name=label,
                    marker=dict(color=ENGINE_COLORS.get(color_key, "#999999"), cornerradius=10),
                    text=[f"{v:.2f}" for v in y_vals],
                    textposition="outside",
                    textfont=dict(size=8),
                    width=bar_width,
                ))
            
            # Update layout
            fig.update_layout(
                title=dict(text=test_name, font=dict(size=16, color="black", family="Arial")),
                xaxis=dict(
                    title="Dataset Size (rows)",
                    ticktext=[str(DATASET_SIZE_MAPPING.get(size, size)) for size in dataset_sizes],
                    tickvals=[x_group_centers[size] for size in dataset_sizes],
                    showgrid=False,
                ),
                yaxis=dict(
                    title="Duration (ms)",
                    type="log",
                    showgrid=True,
                    gridwidth=1,
                    gridcolor="rgba(200,200,200,0.3)",
                ),
                barmode="overlay",
                width=1400,
                height=700,
                showlegend=True,
                legend=dict(
                    x=0.5,
                    y=-0.15,
                    xanchor="center",
                    yanchor="top",
                    orientation="h",
                    bgcolor="rgba(255,255,255,0)",
                    bordercolor="rgba(0,0,0,0)",
                    borderwidth=0,
                ),
                font=dict(size=10, family="Arial"),
                plot_bgcolor="white",
                margin=dict(l=70, r=50, t=80, b=120),
            )
            
            fig.update_yaxes(
                type="log",
                tickmode="array",
                tickvals=[1, 10, 100, 1000, 10000, 100000],
                ticktext=["1", "10", "100", "1k", "10k", "100k"]
            )
            
            # Save to PNG
            filename = self.charts_dir / f"{test_name}.png"
            try:
                fig.write_image(
                    str(filename),
                    width=1400,
                    height=700,
                    scale=2,
                )
                logger.info("    ✓ Saved: %s", filename)
            except Exception as exc:
                logger.error("    ✗ Failed to save %s: %s", filename, exc)

    def generate_summary_csv(self) -> None:
        """Generate summary metrics CSV."""
        if self.df is None or self.df.empty:
            logger.warning("No data to generate summary CSV")
            return

        logger.info("Generating summary metrics CSV...")

        summary = (
            self.df.groupby(["engine", "test_name", "indexed", "dataset_size"])["duration_ms"]
            .agg(["mean", "median", "min", "max", "std", "count"])
            .reset_index()
        )

        summary.columns = ["engine", "test_name", "indexed", "dataset_size", "avg_ms", "median_ms", "min_ms", "max_ms", "stdev_ms", "samples"]
        summary = summary.round(4)

        filename = self.results_dir / "summary_metrics.csv"
        summary.to_csv(filename, index=False)
        logger.info("Saved: %s", filename)

        # Also save as markdown
        md_filename = self.results_dir / "summary_metrics.md"
        with open(md_filename, "w", encoding="utf-8") as fh:
            fh.write("# Benchmark Summary Metrics\n\n")
            fh.write(summary.to_markdown(index=False))
        logger.info("Saved: %s", md_filename)

    def generate_all(self) -> None:
        """Generate all visualizations."""
        logger.info("Generating all visualizations...")
        self.generate_per_test_charts()
        self.generate_summary_csv()
        logger.info("✓ All visualizations generated")


def generate_all_visualizations(result_files: List[str], results_dir: str) -> None:
    """Main entry point for generating visualizations."""
    visualizer = BenchmarkVisualizer(results_dir)
    visualizer.load_results(result_files)
    visualizer.generate_all()
