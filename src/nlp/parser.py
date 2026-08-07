r"""
src/nlp/parser.py
-----------------
Day 29 — NLP Analysis Text Parser

Parses text CAGR/ROE fields from the `analysis` table into structured numeric records,
logs all non-matching entries to a failure report, and cross-validates parsed CAGR
values against the engine-computed values in output/cagr_full.csv.

Design decisions (architect-locked — do not change without sprint review):
    Regex pattern:
        r'(\d+)\s*[Yy]ears?:?\s*([\d.]+)%'
        Handles observed format variations:
            '10 Years: 21%'           — standard
            '5 Years:       24%'      — colon + extra spaces
            '10 Years:     11%   '    — trailing whitespace
            '     5 Years:       8%'  — leading whitespace
            '5 Years          14%'    — missing colon (roe field observed in sample)
        findall() extracts ALL pairs per cell; a cell with multiple windows (e.g.
        "10 Years: 21% 5 Years: 15%") produces multiple output rows correctly.

    Cross-validation scope (architect-mandated):
        ONLY compounded_sales_growth  → sales_{n}yr_cagr   (from cagr_full.csv)
             compounded_profit_growth → net_profit_{n}yr_cagr (from cagr_full.csv)
        stock_price_cagr and roe: parsed and stored, divergence_pct left NULL.
        Source: output/cagr_full.csv ONLY — financial_ratios table has 5yr only;
        cagr_full.csv is the sole artifact with 3yr/5yr/10yr windows.

    SENTINEL_TTM: analysis table has one row per company (company_id PK), no year
        column — TTM exclusion is not applicable at the parser level.
        TTM is handled downstream in trend-based rules.

    Failure logging: every non-matching field is logged; zero silent drops.
        reason codes: NO_MATCH, NULL_INPUT.

    Divergence flag threshold: CAGR_DIVERGENCE_FLAG_PCT from .env (default 5.0).
        Written back as 'divergence_pct' and 'flagged_for_review' columns in
        analysis_parsed.csv, NULL for stock_price_cagr / roe rows.

Metric type mapping (internal canonical names):
    compounded_sales_growth  → 'sales_growth'
    compounded_profit_growth → 'profit_growth'
    stock_price_cagr         → 'stock_price_cagr'
    roe                      → 'roe'

CAGR column mapping for cross-validation (cagr_full.csv):
    sales_growth  + period 10 → sales_10yr_cagr
    sales_growth  + period 5  → sales_5yr_cagr
    sales_growth  + period 3  → sales_3yr_cagr
    profit_growth + period 10 → net_profit_10yr_cagr
    profit_growth + period 5  → net_profit_5yr_cagr
    profit_growth + period 3  → net_profit_3yr_cagr
"""

import os
import re
import logging
from typing import Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — sourced from .env, never hardcoded
# ---------------------------------------------------------------------------

CAGR_DIVERGENCE_FLAG_PCT: float = float(os.getenv("CAGR_DIVERGENCE_FLAG_PCT", "5.0"))

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Canonical metric_type values written to analysis_parsed.csv
METRIC_SALES_GROWTH = "sales_growth"
METRIC_PROFIT_GROWTH = "profit_growth"
METRIC_STOCK_PRICE_CAGR = "stock_price_cagr"
METRIC_ROE = "roe"

# Which analysis table columns map to which metric_type
_FIELD_TO_METRIC: dict[str, str] = {
    "compounded_sales_growth": METRIC_SALES_GROWTH,
    "compounded_profit_growth": METRIC_PROFIT_GROWTH,
    "stock_price_cagr": METRIC_STOCK_PRICE_CAGR,
    "roe": METRIC_ROE,
}

# Only these metric types are cross-validated (engine counterparts exist in cagr_full.csv)
_CROSS_VALIDATE_METRICS = {METRIC_SALES_GROWTH, METRIC_PROFIT_GROWTH}

# cagr_full.csv column names for cross-validation lookup
# key: (metric_type, period_years) → cagr_full.csv column
_CAGR_FULL_COL_MAP: dict[tuple[str, int], str] = {
    (METRIC_SALES_GROWTH, 3): "sales_3yr_cagr",
    (METRIC_SALES_GROWTH, 5): "sales_5yr_cagr",
    (METRIC_SALES_GROWTH, 10): "sales_10yr_cagr",
    (METRIC_PROFIT_GROWTH, 3): "net_profit_3yr_cagr",
    (METRIC_PROFIT_GROWTH, 5): "net_profit_5yr_cagr",
    (METRIC_PROFIT_GROWTH, 10): "net_profit_10yr_cagr",
}

# Compiled regex — handles all observed format variations (see module docstring)
_CAGR_PATTERN = re.compile(
    r"(\d+)\s*[Yy]ears?:?\s*([\d.]+)%",
    re.IGNORECASE,
)

# Failure reason codes
_REASON_NO_MATCH = "NO_MATCH"
_REASON_NULL_INPUT = "NULL_INPUT"


# ---------------------------------------------------------------------------
# Deliverable 1: parse_analysis_text() — pure scalar function
# ---------------------------------------------------------------------------


def parse_analysis_text(raw_text: Optional[str]) -> list[tuple[int, float]]:
    """
    Extract all (period_years, value_pct) pairs from a single raw analysis cell.

    Args:
        raw_text: Raw string from analysis table cell (e.g. '10 Years: 21%').
                  May be None/NaN or an empty string.

    Returns:
        List of (period_years: int, value_pct: float) tuples.
        Returns an empty list (not None, not an exception) for:
            - None / NaN / empty input
            - text that does not match the regex pattern
        An empty list signals a failure to the caller for logging.

    Examples:
        parse_analysis_text('10 Years: 21%')         → [(10, 21.0)]
        parse_analysis_text('5 Years          14%')  → [(5, 14.0)]
        parse_analysis_text('10 Years:     11%   ')  → [(10, 11.0)]
        parse_analysis_text(None)                    → []
        parse_analysis_text('N/A')                   → []
    """
    if raw_text is None or (isinstance(raw_text, float) and pd.isna(raw_text)):
        return []
    text = str(raw_text).strip()
    if not text:
        return []
    matches = _CAGR_PATTERN.findall(text)
    return [(int(period), float(value)) for period, value in matches]


# ---------------------------------------------------------------------------
# Deliverable 2: parse_analysis_table() — bulk in-memory processor
# ---------------------------------------------------------------------------


def parse_analysis_table(
    analysis_df: pd.DataFrame,
    companies_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parse all rows from the `analysis` table (already loaded as a DataFrame).
    Zero DB calls inside this function — callers bulk-load once.

    Args:
        analysis_df:  Full `analysis` table as DataFrame.
                      Required columns: company_id, compounded_sales_growth,
                      compounded_profit_growth, stock_price_cagr, roe.
        companies_df: Full `companies` table as DataFrame (company_id column).
                      Used only to detect companies with no analysis row (logged
                      as failures in parse_failures.csv for audit visibility).

    Returns:
        Tuple of (parsed_df, failures_df):

        parsed_df  — columns: company_id, metric_type, period_years, value_pct,
                               divergence_pct (NULL until cross_validate_cagr()),
                               flagged_for_review (NULL until cross_validate_cagr())
        failures_df — columns: company_id, metric_type, raw_text, reason
    """
    parsed_records: list[dict] = []
    failure_records: list[dict] = []

    # Build lookup: company_id → analysis row (one row per company, PK)
    analysis_by_cid: dict[str, pd.Series] = {}
    if not analysis_df.empty:
        for _, row in analysis_df.iterrows():
            analysis_by_cid[row["company_id"]] = row

    all_company_ids = companies_df["id"].tolist()

    for cid in all_company_ids:
        if cid not in analysis_by_cid:
            # No analysis row at all for this company — log once per missing metric
            for field, metric_type in _FIELD_TO_METRIC.items():
                failure_records.append(
                    {
                        "company_id": cid,
                        "metric_type": metric_type,
                        "raw_text": None,
                        "reason": _REASON_NULL_INPUT,
                    }
                )
            continue

        analysis_row = analysis_by_cid[cid]

        for field, metric_type in _FIELD_TO_METRIC.items():
            raw_text = analysis_row.get(field)

            # None / NaN check
            if raw_text is None or (
                not isinstance(raw_text, str) and pd.isna(raw_text)
            ):
                failure_records.append(
                    {
                        "company_id": cid,
                        "metric_type": metric_type,
                        "raw_text": None,
                        "reason": _REASON_NULL_INPUT,
                    }
                )
                continue

            pairs = parse_analysis_text(raw_text)

            if not pairs:
                # Text present but no regex match — log failure, not exception
                failure_records.append(
                    {
                        "company_id": cid,
                        "metric_type": metric_type,
                        "raw_text": str(raw_text),
                        "reason": _REASON_NO_MATCH,
                    }
                )
                logger.warning(
                    "PARSE_FAILURE [%s / %s]: no match in %r",
                    cid,
                    metric_type,
                    raw_text,
                )
                continue

            for period_years, value_pct in pairs:
                parsed_records.append(
                    {
                        "company_id": cid,
                        "metric_type": metric_type,
                        "period_years": period_years,
                        "value_pct": value_pct,
                        "divergence_pct": None,  # populated by cross_validate_cagr()
                        "flagged_for_review": None,  # populated by cross_validate_cagr()
                    }
                )
                logger.debug(
                    "PARSED [%s / %s / %dyr]: %.2f%%",
                    cid,
                    metric_type,
                    period_years,
                    value_pct,
                )

    parsed_df = pd.DataFrame(
        parsed_records,
        columns=[
            "company_id",
            "metric_type",
            "period_years",
            "value_pct",
            "divergence_pct",
            "flagged_for_review",
        ],
    )
    failures_df = pd.DataFrame(
        failure_records,
        columns=["company_id", "metric_type", "raw_text", "reason"],
    )

    logger.info(
        "parse_analysis_table: %d parsed records, %d failure records",
        len(parsed_df),
        len(failures_df),
    )
    return parsed_df, failures_df


# ---------------------------------------------------------------------------
# Deliverable 3: cross_validate_cagr() — divergence checker
# ---------------------------------------------------------------------------


def cross_validate_cagr(
    parsed_df: pd.DataFrame,
    cagr_full_df: pd.DataFrame,
    tolerance_pct: float = CAGR_DIVERGENCE_FLAG_PCT,
) -> pd.DataFrame:
    """
    Cross-validate parsed sales_growth and profit_growth values against
    engine-computed CAGRs from output/cagr_full.csv.

    Scope (architect-mandated):
        - ONLY metric_type IN {'sales_growth', 'profit_growth'}
        - stock_price_cagr and roe rows: divergence_pct and flagged_for_review
          remain NULL (no engine counterpart in cagr_full.csv).

    Args:
        parsed_df:    Output of parse_analysis_table() — mutated in-place and returned.
        cagr_full_df: Full cagr_full.csv loaded as DataFrame.
                      Must have company_id and columns matching _CAGR_FULL_COL_MAP values.
        tolerance_pct: Divergence threshold from .env CAGR_DIVERGENCE_FLAG_PCT (default 5.0%).

    Returns:
        Updated parsed_df with 'divergence_pct' and 'flagged_for_review' columns populated
        for rows where a cagr_full.csv counterpart exists.
        flagged_for_review: True if abs(divergence_pct) > tolerance_pct, else False.
        divergence_pct: (parsed_value - engine_value). Positive = parsed > engine.
        Both remain None for stock_price_cagr / roe rows.

    Notes:
        - Engine values with CAGR flags (INSUFFICIENT, ZERO_BASE, etc.) have NaN
          as numeric value — divergence is set to NaN, flagged_for_review = False.
        - Zero division guard: if engine_value ≈ 0, divergence_pct = NaN.
    """
    if parsed_df.empty:
        return parsed_df

    # Build a lookup dict: company_id → {col_name: value} from cagr_full
    cagr_lookup: dict[str, dict[str, Optional[float]]] = {}
    if not cagr_full_df.empty:
        for _, row in cagr_full_df.iterrows():
            cid = row["company_id"]
            cagr_lookup[cid] = row.to_dict()

    divergence_pcts: list[Optional[float]] = []
    flagged_list: list[Optional[bool]] = []

    for _, row in parsed_df.iterrows():
        metric_type = row["metric_type"]
        period_years = int(row["period_years"])
        cid = row["company_id"]
        parsed_value = row["value_pct"]

        # stock_price_cagr and roe: no engine counterpart — leave NULL
        if metric_type not in _CROSS_VALIDATE_METRICS:
            divergence_pcts.append(None)
            flagged_list.append(None)
            continue

        # Look up the correct cagr_full.csv column
        col_key = (metric_type, period_years)
        cagr_col = _CAGR_FULL_COL_MAP.get(col_key)

        if cagr_col is None:
            # Period not in {3, 5, 10} — no column exists in cagr_full.csv
            divergence_pcts.append(None)
            flagged_list.append(None)
            continue

        company_cagr = cagr_lookup.get(cid)
        if company_cagr is None:
            # Company not in cagr_full.csv (shouldn't happen for 92 companies)
            logger.warning(
                "CROSS_VALIDATE: company_id %r not found in cagr_full.csv", cid
            )
            divergence_pcts.append(None)
            flagged_list.append(None)
            continue

        engine_value = company_cagr.get(cagr_col)

        # Engine value is NaN/None (flagged CAGR) — skip divergence
        if engine_value is None or (
            isinstance(engine_value, float) and pd.isna(engine_value)
        ):
            divergence_pcts.append(None)
            flagged_list.append(False)
            continue

        engine_value = float(engine_value)

        # Zero-division guard: engine value ≈ 0
        if abs(engine_value) < 1e-6:
            divergence_pcts.append(None)
            flagged_list.append(False)
            continue

        # Divergence: parsed minus engine
        divergence = parsed_value - engine_value
        is_flagged = bool(
            abs(divergence) > tolerance_pct
        )  # cast to native bool (not np.bool_)

        divergence_pcts.append(round(divergence, 4))
        flagged_list.append(is_flagged)

        if is_flagged:
            logger.warning(
                "CAGR_DIVERGENCE [%s / %s / %dyr]: parsed=%.2f%% engine=%.2f%% diff=%.2f%%",
                cid,
                metric_type,
                period_years,
                parsed_value,
                engine_value,
                divergence,
            )

    parsed_df = parsed_df.copy()
    parsed_df["divergence_pct"] = divergence_pcts
    parsed_df["flagged_for_review"] = flagged_list

    flagged_count = sum(1 for f in flagged_list if f is True)
    logger.info(
        "cross_validate_cagr: %d rows cross-validated, %d flagged (>%.1f%% divergence)",
        len(parsed_df),
        flagged_count,
        tolerance_pct,
    )
    return parsed_df
