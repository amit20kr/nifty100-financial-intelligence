"""
src/analytics/ratios.py
-----------------------
Pure-function profitability, leverage, and efficiency ratio formulas.
No I/O inside functions. All thresholds sourced from environment variables.

EBIT Architect Decision:
    EBIT = profit_before_tax + interest
    This is derived (not a raw column). Both source columns exist in
    profitandloss: profit_before_tax, interest. Documented here for auditability.

FINANCIALS_SECTOR_LABEL:
    Sourced from env var FINANCIALS_SECTOR_LABEL (default "Financials").
    Must match sectors.broad_sector exactly. One constant used everywhere;
    never a string literal in formula code.

composite_quality_score (Sprint 2 interim):
    Defined as CFO/PAT 5-year average (raw ratio, not 0-100 scale).
    Implemented in Day 11's cashflow_kpis.py. Sprint 3 introduces the true
    composite health score as a separate column/artifact.

Day 12 Population Notes:
    - DebtEquityResult.high_leverage_flag: Python bool -> SQLite INTEGER.
      Insert layer must use int(result.high_leverage_flag).
    - IcrResult.at_risk_flag: Python Optional[bool] -> SQLite NULL or 0/1.
      Insert layer: int(v) if v is not None else None.
    - net_debt_cr: negative values (net cash position) are valid — no abs().
"""

import logging
import os
from typing import Optional, NamedTuple
import pandas as pd

# ---------------------------------------------------------------------------
# Sector label — single source of truth, never a string literal in formulas
# ---------------------------------------------------------------------------
FINANCIALS_SECTOR_LABEL: str = os.getenv("FINANCIALS_SECTOR_LABEL", "Financials")

# ---------------------------------------------------------------------------
# Edge-case logger (OPM mismatch, ratio anomalies)
# ---------------------------------------------------------------------------
edge_logger = logging.getLogger("ratio_edge_cases")
edge_logger.setLevel(logging.INFO)

log_file_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "output",
    "ratio_edge_cases.log",
)
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

if not edge_logger.handlers:
    fh = logging.FileHandler(log_file_path)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    edge_logger.addHandler(fh)


def _log_opm_mismatch(
    company_id: str, year: str, computed: float, source: float, diff: float
) -> None:
    """Log when computed OPM significantly differs from the source OPM column."""
    edge_logger.info(
        f"OPM Mismatch | {company_id} | {year} | "
        f"Computed: {computed:.2f}% | Source: {source:.2f}% | Diff: {diff:.2f}%"
    )


# ---------------------------------------------------------------------------
# NamedTuple return types — all multi-value returns use these, never plain dict
# ---------------------------------------------------------------------------


class RoceResult(NamedTuple):
    """Return type for return_on_capital_employed()."""

    value: Optional[
        float
    ]  # EBIT / (equity + reserves + borrowings) * 100; None if invalid
    sector_category: (
        str  # "Financials" | "Non-Financials" — from FINANCIALS_SECTOR_LABEL
    )


class DebtEquityResult(NamedTuple):
    """Return type for debt_to_equity()."""

    value: float  # 0.0 if debt-free; never None
    high_leverage_flag: Optional[
        bool
    ]  # True if D/E > threshold AND not Financials; None for Financials sector
    # Day 12: int(result.high_leverage_flag) if not None, else None, before SQLite insert


class IcrResult(NamedTuple):
    """Return type for interest_coverage_ratio()."""

    value: Optional[float]  # None if interest == 0 (debt-free)
    label: Optional[str]  # "Debt Free" if interest == 0; None otherwise
    at_risk_flag: Optional[
        bool
    ]  # True if ICR < threshold; None if debt-free (not evaluated)
    # Day 12: int(v) if v is not None else None before SQLite insert


# ---------------------------------------------------------------------------
# Day 08 — Profitability Ratios
# ---------------------------------------------------------------------------


def net_profit_margin(
    net_profit: Optional[float], sales: Optional[float]
) -> Optional[float]:
    """
    NPM = net_profit / sales * 100
    Returns None if sales == 0 or NaN.
    Negative net_profit returns valid negative margin.
    """
    if pd.isna(sales) or sales == 0:
        return None
    if pd.isna(net_profit):
        return None
    return (net_profit / sales) * 100


def operating_profit_margin(
    operating_profit: Optional[float],
    sales: Optional[float],
    opm_pct_source: Optional[float] = None,
    company_id: str = "UNKNOWN",
    year: str = "UNKNOWN",
) -> Optional[float]:
    """
    OPM = operating_profit / sales * 100
    Returns None if sales == 0 or NaN.
    Cross-checks against opm_pct_source if provided; logs if diff > tolerance.
    Tolerance sourced from OPM_CROSS_CHECK_TOLERANCE_PCT env var (default 1.0).
    """
    if pd.isna(sales) or sales == 0:
        return None
    if pd.isna(operating_profit):
        return None

    computed = (operating_profit / sales) * 100

    if opm_pct_source is not None and not pd.isna(opm_pct_source):
        tolerance = float(os.getenv("OPM_CROSS_CHECK_TOLERANCE_PCT", "1.0"))
        diff = abs(computed - opm_pct_source)
        if diff > tolerance:
            _log_opm_mismatch(company_id, year, computed, opm_pct_source, diff)

    return computed


def return_on_equity(
    net_profit: Optional[float],
    equity_capital: Optional[float],
    reserves: Optional[float],
) -> Optional[float]:
    """
    ROE = net_profit / (equity_capital + reserves) * 100
    Returns None if denominator <= 0 or either component is NaN.
    Negative net_profit returns valid negative ROE (only denominator triggers None).
    """
    if pd.isna(equity_capital) or pd.isna(reserves):
        return None
    denom = equity_capital + reserves
    if denom <= 0:
        return None
    if pd.isna(net_profit):
        return None
    return (net_profit / denom) * 100


def return_on_capital_employed(
    profit_before_tax: Optional[float],
    interest: Optional[float],
    equity_capital: Optional[float],
    reserves: Optional[float],
    borrowings: Optional[float],
    broad_sector: str = "",
) -> RoceResult:
    """
    EBIT = profit_before_tax + interest  (architect decision, see module docstring)
    ROCE = EBIT / (equity_capital + reserves + borrowings) * 100

    Returns RoceResult(value, sector_category).
    value is None if any required input is NaN or denominator <= 0.
    Negative EBIT returns valid negative ROCE.
    sector_category is determined from FINANCIALS_SECTOR_LABEL env constant.
    """
    sector_category = (
        "Financials" if broad_sector == FINANCIALS_SECTOR_LABEL else "Non-Financials"
    )

    if pd.isna(equity_capital) or pd.isna(reserves) or pd.isna(borrowings):
        return RoceResult(value=None, sector_category=sector_category)

    denom = equity_capital + reserves + borrowings
    if denom <= 0:
        return RoceResult(value=None, sector_category=sector_category)

    if pd.isna(profit_before_tax) or pd.isna(interest):
        return RoceResult(value=None, sector_category=sector_category)

    ebit = profit_before_tax + interest
    roce = (ebit / denom) * 100
    return RoceResult(value=roce, sector_category=sector_category)


def return_on_assets(
    net_profit: Optional[float],
    total_assets: Optional[float],
) -> Optional[float]:
    """
    ROA = net_profit / total_assets * 100
    Returns None if total_assets == 0 or NaN.
    """
    if pd.isna(total_assets) or total_assets == 0:
        return None
    if pd.isna(net_profit):
        return None
    return (net_profit / total_assets) * 100


# ---------------------------------------------------------------------------
# Day 09 — Leverage & Efficiency Ratios
# ---------------------------------------------------------------------------


def debt_to_equity(
    borrowings: Optional[float],
    equity_capital: Optional[float],
    reserves: Optional[float],
    broad_sector: str = "",
) -> Optional[DebtEquityResult]:
    """
    D/E = borrowings / (equity_capital + reserves)
    Returns DebtEquityResult(value=0.0, high_leverage_flag=False) if borrowings == 0 or NaN.
    Returns None if equity denominator <= 0 or either component is NaN.
    high_leverage_flag is True only if D/E > DE_HIGH_LEVERAGE_THRESHOLD AND
        broad_sector != FINANCIALS_SECTOR_LABEL (flag suppressed for Financials).
    Threshold from DE_HIGH_LEVERAGE_THRESHOLD env var (default 5.0).
    """
    is_financials = broad_sector == FINANCIALS_SECTOR_LABEL

    # Debt-free case
    if pd.isna(borrowings) or borrowings == 0:
        return DebtEquityResult(
            value=0.0, high_leverage_flag=None if is_financials else False
        )

    if pd.isna(equity_capital) or pd.isna(reserves):
        return None

    denom = equity_capital + reserves
    if denom <= 0:
        return None

    value = borrowings / denom
    threshold = float(os.getenv("DE_HIGH_LEVERAGE_THRESHOLD", "5.0"))
    # Financials -> flag is NULL (not applicable); others -> True/False
    high_leverage_flag = None if is_financials else (value > threshold)

    return DebtEquityResult(value=value, high_leverage_flag=high_leverage_flag)


def interest_coverage_ratio(
    operating_profit: Optional[float],
    other_income: Optional[float],
    interest: Optional[float],
) -> IcrResult:
    """
    ICR = (operating_profit + other_income) / interest
    Returns IcrResult(value=None, label="Debt Free", at_risk_flag=None) if interest == 0 or NaN.
        at_risk_flag is None (not False) for debt-free companies — they are not evaluated,
        which is semantically distinct from "evaluated and found safe".
    Returns IcrResult(value=computed, label=None, at_risk_flag=bool) otherwise.
    at_risk_flag is True if ICR < ICR_AT_RISK_THRESHOLD (default 1.5).
    """
    if pd.isna(interest) or interest == 0:
        return IcrResult(value=None, label="Debt Free", at_risk_flag=None)

    if pd.isna(operating_profit) or pd.isna(other_income):
        return IcrResult(value=None, label=None, at_risk_flag=None)

    computed = (operating_profit + other_income) / interest
    threshold = float(os.getenv("ICR_AT_RISK_THRESHOLD", "1.5"))
    at_risk = computed < threshold

    return IcrResult(value=computed, label=None, at_risk_flag=at_risk)


def net_debt(
    borrowings: Optional[float],
    investments: Optional[float],
) -> Optional[float]:
    """
    Net Debt = borrowings - investments
    Negative result (investments > borrowings) = net cash position — valid, not an error.
    Returns None if either input is NaN.
    """
    if pd.isna(borrowings) or pd.isna(investments):
        return None
    return borrowings - investments


def asset_turnover(
    sales: Optional[float],
    total_assets: Optional[float],
) -> Optional[float]:
    """
    Asset Turnover = sales / total_assets
    Returns None if total_assets == 0 or NaN.
    """
    if pd.isna(total_assets) or total_assets == 0:
        return None
    if pd.isna(sales):
        return None
    return sales / total_assets
