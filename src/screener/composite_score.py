"""
src/screener/composite_score.py
===============================
Day 17 — Composite Quality Score (0–100) and sector-relative ranking.

FORMULA (spec-exact weights):
    35% Profitability:  ROE (15%) + ROCE (10%) + NPM (10%)
    30% Cash Quality:   FCF CAGR 5yr (15%) + CFO/PAT ratio (10%) + FCF positive flag (5%)
    20% Growth:         Revenue CAGR 5yr (10%) + PAT CAGR 5yr (10%)
    15% Leverage:       D/E score (10%) + ICR score (5%)

NORMALISATION: P10/P90 winsorisation → linear scale to [0, 100].

LOCKED DECISIONS (Sprint 3, Day 17):

  1. Naming collision resolution:
     - Existing `composite_quality_score` in financial_ratios = Sprint 2 Day 11
       CFO/PAT trailing-5yr rolling average. Range: −14 to +15. PRESERVED AS-IS.
     - New column: `screener_composite_score` (0–100 scale). Added to engine DataFrame,
       NOT persisted to SQLite (computed on-the-fly).

  2. Binary sub-metric exemption:
     FCF positive flag is binary (0/1). Running it through P10/P90 is unsafe because
     >90% or <10% concentration collapses the scale. Direct map: 1→100, 0→0.

  3. D/E percentile bounds computed on NON-FINANCIALS only:
     Financials companies (D/E up to ~15) would compress genuine leverage differentiation
     among the 69 non-Financials companies. Financials get a flat D/E score of 50 (neutral).
     P10/P90 bounds computed on non-Financials rows only.

  4. P10/P90 computed on NON-NULL values only:
     Null sub-metrics get score 0 afterward. Including nulls as implied zeros would
     distort the P10 bound downward for metrics with real coverage (e.g., PAT CAGR:
     83 non-null out of 92).

  5. Sector-relative percentile rank flagging:
     Sectors with n<5 companies (Real Estate: 2, Communication Services: 2) get their
     sector_relative_score computed but a flag `sector_score_flag = 'SMALL_SECTOR'` is
     set, consistent with the project's "no peer group assigned" graceful-degradation pattern.

  6. FCF CAGR edge case labeling:
     Non-computable FCF CAGR (DECLINE_TO_LOSS, TURNAROUND, BOTH_NEGATIVE) scores 0 and
     gets `fcf_cagr_5yr_flag` set to the CagrFlag enum name. INSUFFICIENT (missing data)
     also scores 0 but gets a distinct flag. An analyst reading screener_output.xlsx can
     tell "penalized for cash-flow deterioration" apart from "no data available."

  7. Universe is 92 companies (engine.df), not 91:
     SIEMENS (Sep FYE, anchor '2024-09') has full data for all 10 composite sub-metrics.
     It MUST receive a non-NULL screener_composite_score.

  8. Winsorization computed ONCE, universe-wide:
     The same P10/P90 bounds are reused across all 6 preset sheets — don't recompute
     per-sheet, which would make cross-preset composite scores non-comparable.

  9. FCF CAGR computation via BULK-LOAD, not per-company DB round-trip:
     A single query loads all FCF history into an in-memory per-company dict. The pure
     extract_cagr_window()/calculate_cagr() functions then operate on in-memory DataFrames.
     This consolidates the per-row anti-pattern from Day 16's Turnaround Watch.

Author: Bluestock Data Analytics Team
Sprint: 3 — Day 17
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.analytics.cagr import CagrResult, calculate_cagr, extract_cagr_window
from src.analytics.constants import CagrFlag

log = logging.getLogger(__name__)

FINANCIALS_LABEL: str = os.getenv("FINANCIALS_SECTOR_LABEL", "Financials")
SECTOR_MIN_SIZE: int = 5  # minimum sector size for reliable percentile ranking


# ---------------------------------------------------------------------------
# Sub-metric weights (spec-exact)
# ---------------------------------------------------------------------------
WEIGHTS: Dict[str, float] = {
    "roe": 0.15,
    "roce": 0.10,
    "npm": 0.10,
    "fcf_cagr": 0.15,
    "cfo_pat": 0.10,
    "fcf_positive": 0.05,
    "rev_cagr": 0.10,
    "pat_cagr": 0.10,
    "de_score": 0.10,
    "icr_score": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


# ---------------------------------------------------------------------------
# winsorise_and_scale — P10/P90 normalisation for continuous metrics
# ---------------------------------------------------------------------------
def winsorise_and_scale(
    values: pd.Series,
    lower_pct: float = 10.0,
    upper_pct: float = 90.0,
    invert: bool = False,
) -> pd.Series:
    """
    Winsorise at P10/P90 and linearly scale to [0, 100].

    Args:
        values:    Continuous metric series (may contain NaN — handled by caller).
        lower_pct: Lower percentile for clipping (default 10).
        upper_pct: Upper percentile for clipping (default 90).
        invert:    If True, lower raw values map to higher scores (e.g., D/E).

    Returns:
        Series of scores in [0, 100]. NaN inputs produce NaN outputs.

    IMPORTANT: Caller must pre-filter to non-null values for P10/P90 computation,
    then apply this function. Nulls should be scored 0 afterward by the caller.
    """
    p_low = np.nanpercentile(values.dropna(), lower_pct)
    p_high = np.nanpercentile(values.dropna(), upper_pct)

    clipped = values.clip(lower=p_low, upper=p_high)

    if abs(p_high - p_low) < 1e-12:
        # Degenerate case: P10 == P90. All non-null values get 50 (midpoint).
        return clipped.where(clipped.isna(), 50.0)

    if invert:
        scaled = (p_high - clipped) / (p_high - p_low) * 100.0
    else:
        scaled = (clipped - p_low) / (p_high - p_low) * 100.0

    return scaled.clip(0.0, 100.0)


# ---------------------------------------------------------------------------
# Bulk-load FCF history and compute 5yr CAGR for all companies
# ---------------------------------------------------------------------------
def _bulk_compute_fcf_cagr(
    company_ids: list, db_path: str
) -> Dict[str, Tuple[Optional[float], Optional[str]]]:
    """
    Compute 5yr FCF CAGR for all companies in a single bulk-load operation.

    Returns:
        Dict mapping company_id → (cagr_value, flag_label).
        cagr_value: float percentage or None.
        flag_label: None if computed, CagrFlag name string if edge case.
    """
    with sqlite3.connect(db_path) as conn:
        all_fcf = pd.read_sql_query(
            "SELECT company_id, year, free_cash_flow_cr FROM financial_ratios ORDER BY company_id, year",
            conn,
        )

    results: Dict[str, Tuple[Optional[float], Optional[str]]] = {}

    for cid in company_ids:
        company_df = all_fcf[all_fcf["company_id"] == cid].copy()

        if company_df.empty:
            results[cid] = (None, CagrFlag.INSUFFICIENT.name)
            continue

        start_val, end_val, years, insufficient = extract_cagr_window(
            company_df, window_years=5, metric_col="free_cash_flow_cr"
        )
        cagr_result: CagrResult = calculate_cagr(
            start_val, end_val, years, insufficient_data=insufficient
        )
        flag_name = cagr_result.flag.name if cagr_result.flag else None
        results[cid] = (cagr_result.value, flag_name)

    return results


# ---------------------------------------------------------------------------
# Main: compute_composite_score
# ---------------------------------------------------------------------------
def compute_composite_score(df: pd.DataFrame, db_path: str) -> pd.DataFrame:
    """
    Compute screener_composite_score (0–100) and sector_relative_score for all
    companies in the engine DataFrame.

    Modifies df IN-PLACE by adding columns:
      - screener_composite_score (float, 0–100)
      - sector_relative_score (float, 0–100)
      - sector_score_flag (str: None or 'SMALL_SECTOR')
      - fcf_cagr_5yr (float, percentage — raw CAGR value)
      - fcf_cagr_5yr_flag (str: None or CagrFlag name)
      - cfo_pat_ratio (float)
      - fcf_positive_flag (int, 0/1)

    Args:
        df:      Engine DataFrame (92 companies, all columns from strict LEFT JOIN).
        db_path: Path to nifty100.db for FCF history bulk-load.

    Returns:
        The modified DataFrame (same object, mutated in-place).
    """
    n_companies = len(df)
    log.info("Computing composite score for %d companies", n_companies)

    # -----------------------------------------------------------------------
    # Phase 1: Derive raw sub-metrics not already in the DataFrame
    # -----------------------------------------------------------------------

    # 1a. FCF CAGR 5yr — bulk-loaded, not per-company round-trip
    fcf_cagr_results = _bulk_compute_fcf_cagr(df["company_id"].tolist(), db_path)
    df["fcf_cagr_5yr"] = df["company_id"].map(
        lambda cid: fcf_cagr_results.get(cid, (None, None))[0]
    )
    df["fcf_cagr_5yr_flag"] = df["company_id"].map(
        lambda cid: fcf_cagr_results.get(cid, (None, None))[1]
    )

    # 1b. CFO/PAT ratio
    df["cfo_pat_ratio"] = np.where(
        (df["net_profit"].notna()) & (df["net_profit"].abs() > 1e-6),
        df["cash_from_operations_cr"] / df["net_profit"],
        np.nan,
    )

    # 1c. FCF positive flag (binary: 1 if FCF > 0, 0 otherwise, NaN if FCF is null)
    df["fcf_positive_flag"] = np.where(
        df["free_cash_flow_cr"].notna(),
        (df["free_cash_flow_cr"] > 0).astype(int),
        np.nan,
    )

    # -----------------------------------------------------------------------
    # Phase 2: Score each sub-metric via P10/P90 winsorisation
    # -----------------------------------------------------------------------

    # Masks for sector-specific and null-aware scoring
    is_financials = df["broad_sector"] == FINANCIALS_LABEL
    is_debt_free = df["icr_at_risk_flag"].isna()  # NULL = debt-free

    # --- Profitability pillar (35%) ---
    df["roe_score"] = winsorise_and_scale(df["return_on_equity_pct"])
    df["roe_score"] = df["roe_score"].fillna(0.0)

    df["roce_score"] = winsorise_and_scale(df["return_on_capital_employed_pct"])
    df["roce_score"] = df["roce_score"].fillna(0.0)

    df["npm_score"] = winsorise_and_scale(df["net_profit_margin_pct"])
    df["npm_score"] = df["npm_score"].fillna(0.0)

    # --- Cash Quality pillar (30%) ---
    df["fcf_cagr_score"] = winsorise_and_scale(df["fcf_cagr_5yr"])
    df["fcf_cagr_score"] = df["fcf_cagr_score"].fillna(0.0)

    df["cfo_pat_score"] = winsorise_and_scale(df["cfo_pat_ratio"])
    df["cfo_pat_score"] = df["cfo_pat_score"].fillna(0.0)

    # FCF positive flag: BINARY — exempt from P10/P90, direct map
    df["fcf_positive_score"] = np.where(
        df["fcf_positive_flag"].notna(),
        df["fcf_positive_flag"] * 100.0,  # 1→100, 0→0
        0.0,  # null FCF → score 0
    )

    # --- Growth pillar (20%) ---
    df["revenue_cagr_score"] = winsorise_and_scale(df["revenue_cagr_5yr"])
    df["revenue_cagr_score"] = df["revenue_cagr_score"].fillna(0.0)

    df["pat_cagr_score"] = winsorise_and_scale(df["pat_cagr_5yr"])
    df["pat_cagr_score"] = df["pat_cagr_score"].fillna(0.0)

    # --- Leverage pillar (15%) ---

    # D/E: P10/P90 computed on NON-FINANCIALS only (directive #3)
    non_fin_de = df.loc[~is_financials, "debt_to_equity"]
    df["de_score"] = winsorise_and_scale(non_fin_de, invert=True)
    # Reindex to full index (Financials rows will be NaN from the subset operation)
    df["de_score"] = df["de_score"].reindex(df.index)
    # Override: Financials → 50 (neutral), nulls → 0
    df.loc[is_financials, "de_score"] = 50.0
    df["de_score"] = df["de_score"].fillna(0.0)

    # ICR: debt-free companies get max score (100), rest winsorised
    df["icr_score"] = winsorise_and_scale(df["interest_coverage"])
    df.loc[is_debt_free, "icr_score"] = 100.0  # debt-free = best possible ICR
    df["icr_score"] = df["icr_score"].fillna(0.0)

    # -----------------------------------------------------------------------
    # Phase 3: Weighted composite score
    # -----------------------------------------------------------------------
    df["screener_composite_score"] = (
        df["roe_score"] * WEIGHTS["roe"]
        + df["roce_score"] * WEIGHTS["roce"]
        + df["npm_score"] * WEIGHTS["npm"]
        + df["fcf_cagr_score"] * WEIGHTS["fcf_cagr"]
        + df["cfo_pat_score"] * WEIGHTS["cfo_pat"]
        + df["fcf_positive_score"] * WEIGHTS["fcf_positive"]
        + df["revenue_cagr_score"] * WEIGHTS["rev_cagr"]
        + df["pat_cagr_score"] * WEIGHTS["pat_cagr"]
        + df["de_score"] * WEIGHTS["de_score"]
        + df["icr_score"] * WEIGHTS["icr_score"]
    ).round(2)

    # Pre-aggregate FCF score for radar charts (30% weight)
    df["fcf_score"] = (
        df["fcf_cagr_score"] * WEIGHTS["fcf_cagr"]
        + df["cfo_pat_score"] * WEIGHTS["cfo_pat"]
        + df["fcf_positive_score"] * WEIGHTS["fcf_positive"]
    ) / 0.30

    log.info(
        "Composite score stats: min=%.2f, max=%.2f, mean=%.2f",
        df["screener_composite_score"].min(),
        df["screener_composite_score"].max(),
        df["screener_composite_score"].mean(),
    )

    # -----------------------------------------------------------------------
    # Phase 4: Sector-relative percentile rank
    # -----------------------------------------------------------------------
    sector_counts = df["broad_sector"].value_counts()
    small_sectors = set(sector_counts[sector_counts < SECTOR_MIN_SIZE].index)

    if small_sectors:
        log.warning(
            "Small sectors (n<%d) flagged for unreliable percentile: %s",
            SECTOR_MIN_SIZE,
            small_sectors,
        )

    df["sector_relative_score"] = np.nan
    df["sector_score_flag"] = None

    for sector, group in df.groupby("broad_sector"):
        sector_idx = group.index
        # Percentile rank within sector (0–100)
        sector_pctile = group["screener_composite_score"].rank(pct=True) * 100.0
        df.loc[sector_idx, "sector_relative_score"] = sector_pctile.round(2)

        if sector in small_sectors:
            df.loc[sector_idx, "sector_score_flag"] = "SMALL_SECTOR"

    # -----------------------------------------------------------------------
    # Phase 5: Ensure completeness
    # -----------------------------------------------------------------------

    null_count = df["screener_composite_score"].isna().sum()
    if null_count > 0:
        log.error("%d companies have NULL screener_composite_score!", null_count)

    return df
