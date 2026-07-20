"""
src/analytics/cagr.py
---------------------
CAGR (Compound Annual Growth Rate) engine for Revenue, PAT, and EPS series.

Two public deliverables:
    1. calculate_cagr()       — pure scalar function; no I/O, no DB access
    2. extract_cagr_window()  — window-extraction layer; pulls start/end values
                                from a real company P&L DataFrame by calendar year

Design decisions (architect-locked, do not change without sprint review):

    CAGR formula:
        ((end_val / start_val) ^ (1/years) - 1) * 100

    Zero detection:
        Uses math.isclose(..., abs_tol=CAGR_ZERO_EPSILON) — never exact == 0.
        CAGR_ZERO_EPSILON sourced from env var (default 1e-6), consistent with
        the project's "no hardcoded thresholds" standard (see BS_BALANCE_TOLERANCE_PCT).

    Condition evaluation order in calculate_cagr() (ORDER IS SEMANTICALLY CRITICAL):
        1. years <= 0 guard          → ValueError (never propagate to batch loop)
        2. insufficient_data / NaN   → INSUFFICIENT
        3. start_val ≈ 0             → ZERO_BASE
        4. end_val ≈ 0               → ZERO_END  ← evaluated BEFORE TURNAROUND
        5. both negative             → BOTH_NEGATIVE
        6. start < 0, end > 0        → TURNAROUND
        7. start > 0, end < 0        → DECLINE_TO_LOSS
        8. (default) both positive   → compute, flag=None

    ZERO_END before TURNAROUND:
        start < 0, end ≈ 0  →  ZERO_END  (company at breakeven, not a recovery)
        This is intentional. TURNAROUND requires end_val > 0, which isclose-to-zero
        values do not satisfy after the ZERO_END guard removes them.

    TTM exclusion in extract_cagr_window():
        Targeted filter: series[series['year'] != SENTINEL_TTM]
        NOT a blanket "drop most recent row" — non-TTM companies are unaffected.

    Year matching:
        Uses int(year_str[:4]) to extract the 4-digit calendar year.
        Handles ABB (Dec fiscal year-end, "2024-12"), SIEMENS (Sep, "2024-09"),
        and all other non-March year-ends correctly without special-casing.
        iloc[-n] is strictly forbidden — it silently misaligns on gapped series.

    Day 12 population notes (pre-recorded):
        - Insert result.flag (str Enum) directly into TEXT columns; str(Enum) is safe.
        - 5yr values → SQLite financial_ratios columns.
        - 3yr + 10yr values → output/cagr_full.csv only.
"""

import math
import os
from typing import Optional, NamedTuple

import pandas as pd

from src.analytics.constants import CagrFlag
from src.etl.normaliser import SENTINEL_TTM


# ---------------------------------------------------------------------------
# CAGR zero-detection threshold — sourced from env, never hardcoded
# ---------------------------------------------------------------------------
CAGR_ZERO_EPSILON: float = float(os.getenv("CAGR_ZERO_EPSILON", "1e-6"))


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


class CagrResult(NamedTuple):
    """
    Return type for calculate_cagr().
    value: computed CAGR percentage, or None if any edge case triggered.
    flag:  CagrFlag enum member describing the edge case, or None if computed.
    """

    value: Optional[float]
    flag: Optional[CagrFlag]


# ---------------------------------------------------------------------------
# Deliverable 1: calculate_cagr() — pure scalar function
# ---------------------------------------------------------------------------


def calculate_cagr(
    start_val: Optional[float],
    end_val: Optional[float],
    years: int,
    insufficient_data: bool = False,
) -> CagrResult:
    """
    Compute CAGR: ((end_val / start_val) ^ (1/years) - 1) * 100

    Args:
        start_val:         Value at the start of the window (base year).
        end_val:           Value at the end of the window (most recent fiscal year).
        years:             Number of years in the window (must be > 0).
        insufficient_data: If True, skip all other checks and return INSUFFICIENT.
                           Also raised when start_val or end_val is NaN/None.

    Returns:
        CagrResult(value, flag) — value is None for all edge cases.

    Raises:
        ValueError: if years <= 0. Never propagates a ZeroDivisionError to callers.

    Edge case evaluation order (semantically significant — see module docstring):
        years <= 0        → ValueError
        insufficient/NaN  → INSUFFICIENT
        start ≈ 0         → ZERO_BASE
        end ≈ 0           → ZERO_END
        both < 0          → BOTH_NEGATIVE
        start < 0, end > 0 → TURNAROUND
        start > 0, end < 0 → DECLINE_TO_LOSS
        (default)          → compute, return value, flag=None
    """
    # --- Guard: invalid window size -------------------------------------------
    if years <= 0:
        raise ValueError(
            f"calculate_cagr: years must be > 0, got {years!r}. "
            "This is a caller bug — check extract_cagr_window() output."
        )

    # --- Check 1: Insufficient data -------------------------------------------
    if insufficient_data:
        return CagrResult(value=None, flag=CagrFlag.INSUFFICIENT)

    if start_val is None or end_val is None:
        return CagrResult(value=None, flag=CagrFlag.INSUFFICIENT)

    try:
        if math.isnan(float(start_val)) or math.isnan(float(end_val)):
            return CagrResult(value=None, flag=CagrFlag.INSUFFICIENT)
    except (TypeError, ValueError):
        return CagrResult(value=None, flag=CagrFlag.INSUFFICIENT)

    start_val = float(start_val)
    end_val = float(end_val)

    # --- Check 2: Zero base ---------------------------------------------------
    if math.isclose(start_val, 0.0, abs_tol=CAGR_ZERO_EPSILON):
        return CagrResult(value=None, flag=CagrFlag.ZERO_BASE)

    # --- Check 3: Zero end (BEFORE turnaround — see docstring ordering note) --
    if math.isclose(end_val, 0.0, abs_tol=CAGR_ZERO_EPSILON):
        return CagrResult(value=None, flag=CagrFlag.ZERO_END)

    # --- Check 4: Both negative -----------------------------------------------
    if start_val < 0 and end_val < 0:
        return CagrResult(value=None, flag=CagrFlag.BOTH_NEGATIVE)

    # --- Check 5: Turnaround (neg → pos) --------------------------------------
    if start_val < 0 and end_val > 0:
        return CagrResult(value=None, flag=CagrFlag.TURNAROUND)

    # --- Check 6: Decline to loss (pos → neg) ---------------------------------
    if start_val > 0 and end_val < 0:
        return CagrResult(value=None, flag=CagrFlag.DECLINE_TO_LOSS)

    # --- Check 7: Normal computation (both positive) --------------------------
    cagr = (math.pow(end_val / start_val, 1.0 / years) - 1.0) * 100.0
    return CagrResult(value=cagr, flag=None)


# ---------------------------------------------------------------------------
# Deliverable 2: extract_cagr_window() — window-extraction layer
# ---------------------------------------------------------------------------


def extract_cagr_window(
    company_series: pd.DataFrame,
    window_years: int,
    metric_col: str,
) -> tuple:
    """
    Extract (start_val, end_val, actual_years, insufficient_data) from a company's
    P&L DataFrame for a CAGR window computation.

    Args:
        company_series: DataFrame with at minimum columns ['year', metric_col].
                        'year' values are canonical 'YYYY-MM' strings or SENTINEL_TTM.
        window_years:   Number of years to look back (e.g. 3, 5, 10).
        metric_col:     Column to extract values from ('sales', 'net_profit', 'eps').

    Returns:
        Tuple of (start_val, end_val, actual_years, insufficient_data):
            start_val:        float or None — value at start year
            end_val:          float or None — value at end year
            actual_years:     int — equals window_years when data is present (passed
                              directly to calculate_cagr(years=...))
            insufficient_data: bool — True if start or end year row is absent

    Rules (in order of application):
        1. Filter out TTM rows by targeted equality: year != SENTINEL_TTM.
           This is NOT a "drop most recent row" — non-TTM companies are unaffected.
        2. Parse calendar year: int(year_str[:4]).
        3. end_year  = max calendar year in filtered series.
        4. start_year = end_year - window_years.
        5. If either start_year or end_year row is absent → insufficient_data=True.
        6. NaN values in metric_col for a present row → value is None; calculate_cagr
           will classify as INSUFFICIENT.

    Year-matching design:
        Uses int(year_str[:4]) extracted from 'YYYY-MM' — not string equality.
        This correctly handles ABB (year-end Dec: '2024-12'), SIEMENS (Sep: '2024-09')
        and any other non-March fiscal year-end without special-casing.
        iloc[-n] is strictly forbidden — silently misaligns on gapped series.
    """
    if company_series.empty:
        return (None, None, window_years, True)

    # Step 1: Exclude TTM rows (targeted filter, not blanket drop-last)
    fiscal_series = company_series[company_series["year"] != SENTINEL_TTM].copy()

    if fiscal_series.empty:
        return (None, None, window_years, True)

    # Step 2: Parse calendar years from YYYY-MM strings
    try:
        fiscal_series = fiscal_series.copy()
        fiscal_series["_cal_year"] = fiscal_series["year"].apply(
            lambda y: int(str(y)[:4])
        )
    except (ValueError, TypeError):
        return (None, None, window_years, True)

    # Step 3: Determine end_year (most recent fiscal year, excluding TTM)
    end_year = int(fiscal_series["_cal_year"].max())

    # Step 4: Determine start_year by calendar arithmetic
    start_year = end_year - window_years

    # Step 5: Locate rows — by calendar year value, never by row offset
    end_rows = fiscal_series[fiscal_series["_cal_year"] == end_year]
    start_rows = fiscal_series[fiscal_series["_cal_year"] == start_year]

    if end_rows.empty or start_rows.empty:
        return (None, None, window_years, True)

    end_val = end_rows.iloc[0][metric_col]
    start_val = start_rows.iloc[0][metric_col]

    # Convert pandas NA/NaN to None for downstream type safety
    if pd.isna(end_val):
        end_val = None
    if pd.isna(start_val):
        start_val = None

    return (start_val, end_val, window_years, False)
