"""
src/analytics/radar.py
======================
Day 19 — Radar Charts Generation Engine.

Generates an 8-axis radar/polar chart for every Nifty 100 company visualizing their fundamental
profile across 0-100 scaled axes.

Axes:
- ROE Score
- ROCE Score
- NPM Score
- D/E Score (Inverted)
- FCF Score (Aggregated)
- PAT CAGR Score
- Revenue CAGR Score
- Composite Score

Architectural Note:
Plots use the universe-wide continuous 0-100 scaled scores (from composite_score.py),
NOT peer-relative percentile ranks, to ensure geometrically comparable shapes.
Degenerate peer groups (n <= 1) and unmapped companies fall back to the Nifty 100
universe-wide mean for their dashed comparative overlay.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.screener.engine import FilterEngine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)

AXES_COLS = [
    "roe_score",
    "roce_score",
    "npm_score",
    "de_score",
    "fcf_score",
    "pat_cagr_score",
    "revenue_cagr_score",
    "screener_composite_score",
]

LABELS = [
    "ROE",
    "ROCE",
    "Net Profit Margin",
    "D/E (Inverted)",
    "FCF Score",
    "PAT CAGR",
    "Revenue CAGR",
    "Composite Score",
]


def sanitize_filename(name: str) -> str:
    """Sanitize company ticker for filesystem safety (e.g. M&M -> M_M)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def get_peer_group_averages(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Computes the mean score for each peer group. Identifies degenerate groups."""
    group_sizes = df.groupby("peer_group_name").size()
    valid_groups = group_sizes[group_sizes > 1].index.tolist()

    averages = {}
    for group in valid_groups:
        group_df = df[df["peer_group_name"] == group]
        averages[group] = group_df[AXES_COLS].mean()

    return averages


def generate_radar_charts(
    db_path: Path = Path("db/nifty100.db"), out_dir: Path = Path("reports/radar_charts")
):
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Initialize Engine (Computes 0-100 scores internally)
    logger.info("Initializing FilterEngine to compute 0-100 scores...")
    engine = FilterEngine(config_path="config/screener_config.yaml", db_path=db_path)
    df = engine.df

    # 2. Join with peer_groups from SQLite to get group mapping
    with sqlite3.connect(db_path) as conn:
        pg_df = pd.read_sql_query(
            "SELECT company_id, peer_group_name FROM peer_groups", conn
        )

    df = df.merge(pg_df, on="company_id", how="left")

    # 3. Compute Averages
    universe_avg = df[AXES_COLS].mean()
    peer_averages = get_peer_group_averages(df)

    logger.info(f"Generating 8-axis radar charts for {len(df)} companies...")

    num_vars = len(AXES_COLS)
    # Compute angle for each axis
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    # Complete the loop
    angles += angles[:1]

    generated_count = 0
    for _, row in df.iterrows():
        company_id = row["company_id"]
        peer_group = row["peer_group_name"]

        # Decide which overlay to use
        if pd.notna(peer_group) and peer_group in peer_averages:
            overlay_vals = peer_averages[peer_group].tolist()
            overlay_label = f"{peer_group} Average"
        else:
            overlay_vals = universe_avg.tolist()
            overlay_label = "Nifty 100 Average"

        overlay_vals += overlay_vals[:1]

        # Company values
        comp_vals = row[AXES_COLS].tolist()
        # Handle potential NaNs by converting to 0 for plotting
        comp_vals = [v if pd.notna(v) else 0.0 for v in comp_vals]
        comp_vals += comp_vals[:1]

        # Plotting
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True), dpi=300)

        # Draw one axe per variable and add labels
        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        plt.xticks(angles[:-1], LABELS, size=10)

        # Draw ylabels
        ax.set_rlabel_position(0)
        plt.yticks(
            [20, 40, 60, 80, 100], ["20", "40", "60", "80", "100"], color="grey", size=8
        )
        plt.ylim(0, 100)

        # Plot comparative average (dashed)
        ax.plot(
            angles,
            overlay_vals,
            linewidth=1.5,
            linestyle="--",
            color="#7f7f7f",
            label=overlay_label,
        )

        # Plot company (solid)
        ax.plot(
            angles,
            comp_vals,
            linewidth=2,
            linestyle="solid",
            color="#1f77b4",
            label=company_id,
        )
        ax.fill(angles, comp_vals, color="#1f77b4", alpha=0.25)

        plt.title(f"{company_id} Fundamental Profile", size=14, y=1.1)
        plt.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

        # Save and strictly close to avoid memory leak
        safe_filename = sanitize_filename(company_id)
        out_path = out_dir / f"{safe_filename}_radar.png"
        plt.savefig(out_path, bbox_inches="tight")
        plt.close(fig)

        generated_count += 1

    logger.info(f"Successfully generated {generated_count} radar charts in {out_dir}")
    return df


if __name__ == "__main__":
    generate_radar_charts()
