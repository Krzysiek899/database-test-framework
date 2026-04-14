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

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import rcParams

logger = logging.getLogger(__name__)

# Set consistent style
sns.set_style("whitegrid")
rcParams["figure.figsize"] = (12, 7)
rcParams["font.size"] = 10

# Fixed colors per engine (consistent across all charts)
ENGINE_COLORS = {
    "postgres": "#1f77b4",   # blue
    "mongodb": "#ff7f0e",    # orange
    "couchdb": "#2ca02c",    # green
    "mysql": "#d62728",      # red
}


class BenchmarkVisualizer:
    """Generate per-test chart visualizations from benchmark results."""

    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
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

    def _compute_bar_layout(
        self,
        test_data: pd.DataFrame,
    ) -> Dict[Tuple[str, str, bool], Tuple[float, float, str]]:
        """
        Compute bar positions for a single test across all combinations.
        
        Returns dict: (dataset_size, engine, indexed) → (x_position, bar_width, color)
        """
        # Get unique dataset sizes, engines, indexed values
        dataset_sizes = sorted(test_data["dataset_size"].unique())
        engines = sorted(test_data["engine"].unique())
        has_indexed = test_data["indexed"].sum() > 0 and (~test_data["indexed"]).sum() > 0
        
        layout = {}
        bar_width = 0.08
        gap_within_group = 0.02
        gap_between_groups = 0.15
        
        current_x = 0
        
        for size_idx, size in enumerate(dataset_sizes):
            # Space for this group
            if has_indexed:
                # 8 bars: 4 for unindexed, 4 for indexed
                num_bars = 8
            else:
                # 4 bars for engines
                num_bars = 4
            
            group_width = num_bars * bar_width + (num_bars - 1) * gap_within_group
            group_center = current_x + group_width / 2
            
            # Record group center for x-axis label
            if not hasattr(self, "_size_label_positions"):
                self._size_label_positions = {}
            self._size_label_positions[size] = group_center
            
            bar_x = current_x
            
            for engine in engines:
                # Unindexed bar
                layout[(size, engine, False)] = (bar_x, bar_width, ENGINE_COLORS.get(engine, "#999999"))
                bar_x += bar_width + gap_within_group
                
                # Indexed bar (if data exists)
                if has_indexed:
                    layout[(size, engine, True)] = (bar_x, bar_width, ENGINE_COLORS.get(engine, "#999999"))
                    bar_x += bar_width + gap_within_group
            
            # Gap between groups
            current_x = bar_x + gap_between_groups
        
        return layout

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
            
            # Compute layout
            self._size_label_positions = {}
            layout = self._compute_bar_layout(test_data)
            
            # Get aggregated data
            agg_data = (
                test_data.groupby(["dataset_size", "engine", "indexed"])["duration_ms"]
                .mean()
                .reset_index()
            )
            
            # Create figure
            fig, ax = plt.subplots(figsize=(14, 7))
            
            # Plot bars
            legend_items = []
            legend_labels = []
            
            for (size, engine, indexed), (x_pos, width, color) in layout.items():
                # Find data for this combination
                matching = agg_data[
                    (agg_data["dataset_size"] == size) &
                    (agg_data["engine"] == engine) &
                    (agg_data["indexed"] == indexed)
                ]
                
                if matching.empty:
                    continue
                
                duration = matching["duration_ms"].values[0]
                
                # Determine legend label and alpha
                has_indexed_data = (agg_data["indexed"] == True).any()
                if has_indexed_data:
                    label = f"{engine} {'(indexed)' if indexed else '(unindexed)'}"
                    alpha = 0.6 if indexed else 0.9
                else:
                    label = engine
                    alpha = 0.9
                
                bar = ax.bar(x_pos, duration, width=width, color=color, alpha=alpha, edgecolor="black", linewidth=0.5)
                
                # Add to legend (only first occurrence per label)
                if label not in legend_labels:
                    legend_items.append(bar)
                    legend_labels.append(label)
            
            # Set x-axis
            dataset_sizes = sorted(test_data["dataset_size"].unique())
            if dataset_sizes and len(self._size_label_positions) > 0:
                ax.set_xticks([self._size_label_positions[size] for size in dataset_sizes])
                ax.set_xticklabels(dataset_sizes)
            
            # Labels and title
            ax.set_xlabel("Dataset Size", fontsize=11, fontweight="bold")
            ax.set_ylabel("Duration (ms)", fontsize=11, fontweight="bold")
            ax.set_title(test_name, fontsize=13, fontweight="bold")
            ax.legend(legend_items, legend_labels, loc="upper left", fontsize=9)
            ax.grid(axis="y", alpha=0.3, linestyle="--")
            
            plt.tight_layout()
            
            # Save
            filename = self.results_dir / f"{test_name}.png"
            plt.savefig(filename, dpi=300, bbox_inches="tight")
            logger.info("    ✓ Saved: %s", filename)
            plt.close(fig)

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
