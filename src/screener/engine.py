"""
engine.py
=========
Core screening engine for the Nifty 100 Financial Intelligence Platform.

Executes filtering logic over a strict LEFT JOIN architecture anchored to the
latest available fiscal year per company from financial_ratios.
"""

import os
import sqlite3
from typing import Dict, Any
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

from src.screener.config_loader import load_screener_config
from src.screener.composite_score import compute_composite_score

load_dotenv()


class FilterEngine:
    """
    FilterEngine evaluates companies against filtering criteria.

    It constructs a base DataFrame combining financial_ratios, profitandloss,
    market_cap, and sectors via strict LEFT JOINs on the latest fiscal year.
    """

    def __init__(self, db_path: str | Path, config_path: str | Path):
        self.db_path = str(db_path)
        self.config_path = str(config_path)
        self.df = pd.DataFrame()
        self.config: Dict[str, Any] = {}

        self._load_data()
        self._load_config()
        self._compute_scores()

    def _load_data(self) -> None:
        """
        Executes the anchor-year query and strict LEFT JOIN architecture.
        """
        query = """
        WITH AnchorYear AS (
            SELECT 
                company_id, 
                year,
                ROW_NUMBER() OVER (
                    PARTITION BY company_id 
                    ORDER BY 
                        CASE WHEN year LIKE '%-03' THEN 1 ELSE 2 END ASC, 
                        year DESC
                ) as rn
            FROM financial_ratios
        )
        SELECT 
            fr.*,
            pl.sales,
            pl.net_profit,
            mc.market_cap_crore,
            mc.enterprise_value_crore,
            mc.pe_ratio,
            mc.pb_ratio,
            mc.dividend_yield_pct,
            s.broad_sector
        FROM AnchorYear a
        JOIN financial_ratios fr ON a.company_id = fr.company_id AND a.year = fr.year
        LEFT JOIN profitandloss pl ON fr.company_id = pl.company_id AND fr.year = pl.year
        LEFT JOIN market_cap mc ON fr.company_id = mc.company_id AND fr.year = mc.year
        LEFT JOIN sectors s ON fr.company_id = s.company_id
        WHERE a.rn = 1;
        """

        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        with sqlite3.connect(self.db_path) as conn:
            self.df = pd.read_sql_query(query, conn)

    def _load_config(self) -> None:
        """
        Loads and validates the YAML config against the engine's joined column set.
        """
        available_columns = set(self.df.columns)
        self.config = load_screener_config(self.config_path, available_columns)

    def _compute_scores(self) -> None:
        """
        Compute screener_composite_score and sector_relative_score.
        Called once during init; scores are computed universe-wide and reused
        across all preset filter outputs (never recomputed per-sheet).
        """
        compute_composite_score(self.df, self.db_path)

    def apply(self, criteria: Dict[str, float]) -> pd.DataFrame:
        """
        Applies a dictionary of criteria (metric_name -> threshold) to the dataset.

        Args:
            criteria: Dictionary mapping metric names to their numeric thresholds.
                      Example: {"sales": 5000, "debt_to_equity": 1.0}

        Returns:
            A DataFrame of companies passing all specified filters.
        """
        mask = pd.Series(True, index=self.df.index)
        metrics_catalog = self.config["metrics"]

        financials_label = os.getenv("FINANCIALS_SECTOR_LABEL", "Financials")

        for metric_name, threshold in criteria.items():
            if metric_name not in metrics_catalog:
                raise ValueError(f"Unknown metric '{metric_name}' in criteria.")

            cfg = metrics_catalog[metric_name]
            col = cfg["column"]
            operator = cfg["operator"]

            series = self.df[col]

            if operator == "min":
                filter_pass = series >= threshold
            elif operator == "max":
                filter_pass = series <= threshold
            elif operator == "eq":
                filter_pass = series == threshold
            else:
                filter_pass = pd.Series(False, index=self.df.index)

            # --- Edge Cases ---
            if col == "debt_to_equity":
                # Financials D/E Bypass: bypasses the predicate, treating as pass.
                financials_mask = self.df["broad_sector"] == financials_label
                filter_pass = filter_pass | financials_mask

            elif col == "interest_coverage":
                # ICR-as-infinity Bypass: debt-free companies pass automatically.
                debt_free_mask = self.df["icr_at_risk_flag"].isna()
                filter_pass = filter_pass | debt_free_mask

            # Fail-closed handling: pd.Series(NA >= val) is False, but ensure strict boolean mask.
            filter_pass = filter_pass.fillna(False)

            mask &= filter_pass

        return self.df[mask].copy()


if __name__ == "__main__":
    import logging as _logging

    _logging.basicConfig(
        level=_logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
    )

    engine = FilterEngine(
        db_path=Path("db/nifty100.db"), config_path=Path("config/screener_config.yaml")
    )

    res = engine.apply({})
    print(f"Screener engine initialized. Baseline row count: {len(res)}")
    print(
        f"Composite score range: {res['screener_composite_score'].min():.2f} – {res['screener_composite_score'].max():.2f}"
    )
    print(
        f"Sector-relative score range: {res['sector_relative_score'].min():.2f} – {res['sector_relative_score'].max():.2f}"
    )
    print("\nTop 10 by composite score:")
    top = res.nlargest(10, "screener_composite_score")[
        [
            "company_id",
            "broad_sector",
            "screener_composite_score",
            "sector_relative_score",
        ]
    ]
    print(top.to_string(index=False))
