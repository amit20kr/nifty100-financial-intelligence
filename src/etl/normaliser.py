"""
normaliser.py
=============
Field-level normalisation functions for the Nifty 100 ETL pipeline.

All transformations must be deterministic and reversible for audit purposes.
Any unparseable input returns a sentinel value ('PARSE_ERROR' / 'MISSING')
so the downstream schema validator (validator.py) can catch and log it.

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 2
Standard: PEP8 | type hints | one-line docstrings on every public function
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Month-name → zero-padded month-number lookup (handles 3-char abbreviations
# AND full month names, case-insensitive)
# ---------------------------------------------------------------------------
_MONTH_MAP: dict[str, str] = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

# Sentinel values — used as FK-integrity signals downstream
SENTINEL_PARSE_ERROR = "PARSE_ERROR"
SENTINEL_MISSING = "MISSING"
SENTINEL_TTM = "TTM"  # Trailing Twelve Months — valid but non-annual
SENTINEL_PARTIAL = "PARTIAL_YEAR"  # e.g. '9-month' transition periods


# ---------------------------------------------------------------------------
# normalize_year
# ---------------------------------------------------------------------------
def normalize_year(raw: object) -> str:
    """Convert any financial-year label to canonical 'YYYY-MM' format.

    Supported input patterns (case-insensitive):
        - 'Mar-23'  / 'Mar 23'  → '2023-03'
        - 'Mar-2023' / 'Mar 2023' → '2023-03'
        - 'March-2023' / 'March 2023' → '2023-03'
        - 'FY23' / 'FY2023' / 'FY 23' → '2023-03'  (defaults to March close)
        - '2023' (bare 4-digit year) → '2023-03'
        - '2023-03' (already canonical) → '2023-03'
        - 'Dec-22' → '2022-12'  (non-March year-ends handled correctly)
        - NaN / None / empty → SENTINEL_PARSE_ERROR

    Returns:
        Canonical 'YYYY-MM' string or 'PARSE_ERROR' if unparseable.
    """
    # --- Guard: null / missing -------------------------------------------------
    # pd.isna covers: None, float('nan'), pd.NA, pd.NaT
    try:
        if pd.isna(raw):  # type: ignore[arg-type]
            logger.debug("normalize_year received null value → PARSE_ERROR")
            return SENTINEL_PARSE_ERROR
    except (TypeError, ValueError):
        pass  # non-scalar types will be handled below

    raw_str = str(raw).strip()

    if not raw_str:
        return SENTINEL_PARSE_ERROR

    # --- 0a. TTM (Trailing Twelve Months) — preserve as special sentinel ------
    if raw_str.upper() == "TTM":
        logger.debug("normalize_year: TTM label preserved")
        return SENTINEL_TTM

    # --- 0b. Partial-year suffix: 'Mar 2016 9m', 'Mar 2023 15', 'Mar 2016 3q' ----
    # Covers:
    #   - Duration suffixes: 9m, 3q, 6M, 4Q  (month/quarter counts)
    #   - Plain day/number suffix: 'Mar 2023 15' (day-of-period marker)
    partial_match = re.match(
        r"([A-Za-z]+\s+\d{2,4})\s+\d{1,2}[mMqQ]?$",
        raw_str,
    )
    if partial_match:
        raw_str = partial_match.group(1).strip()
        logger.debug("normalize_year: partial-year label stripped → '%s'", raw_str)
        # Fall through to standard month-year parsing below

    # --- 0c. Float year from Excel numeric cell: '2024.5' → truncate to int ----
    # Excel sometimes stores years as floats when a half-year flag is encoded.
    # We truncate to the integer year and default to March FY close.
    float_year_match = re.fullmatch(r"(\d{4})\.\d+", raw_str)
    if float_year_match:
        yr = int(float_year_match.group(1))
        if 2000 <= yr <= 2099:
            logger.debug("normalize_year: float year '%s' truncated → %d", raw_str, yr)
            return f"{yr}-03"
        return SENTINEL_PARSE_ERROR

    # --- 1. Already canonical: YYYY-MM ----------------------------------------
    if re.fullmatch(r"\d{4}-\d{2}", raw_str):
        year, month = raw_str.split("-")
        if 1 <= int(month) <= 12 and 2000 <= int(year) <= 2099:
            return raw_str
        logger.warning("normalize_year: out-of-range canonical '%s'", raw_str)
        return SENTINEL_PARSE_ERROR

    # --- 2. FY-style: FY23, FY2023, FY 23 -------------------------------------
    fy_match = re.fullmatch(r"[Ff][Yy]\s*(\d{2,4})", raw_str)
    if fy_match:
        yr = _expand_short_year(fy_match.group(1))
        if yr:
            return f"{yr}-03"
        return SENTINEL_PARSE_ERROR

    # --- 3. Bare 4-digit year: 2023 -------------------------------------------
    if re.fullmatch(r"\d{4}", raw_str):
        yr = int(raw_str)
        if 2000 <= yr <= 2099:
            return f"{yr}-03"
        return SENTINEL_PARSE_ERROR

    # --- 4. Month-name patterns: Mar-23, Mar 2023, March-2023 -----------------
    # Tolerates separator: space, dash, underscore, forward-slash
    month_year_match = re.fullmatch(r"([A-Za-z]+)[\s\-_/](\d{2,4})", raw_str)
    if month_year_match:
        month_str = month_year_match.group(1).lower()
        year_str = month_year_match.group(2)
        month_num = _MONTH_MAP.get(month_str)
        yr = _expand_short_year(year_str)
        if month_num and yr:
            return f"{yr}-{month_num}"
        logger.warning(
            "normalize_year: unrecognised month '%s' in '%s'", month_str, raw_str
        )
        return SENTINEL_PARSE_ERROR

    # --- Fallback -------------------------------------------------------------
    logger.warning("normalize_year: unparseable input '%s'", raw_str)
    return SENTINEL_PARSE_ERROR


def _expand_short_year(raw_yr: str) -> Optional[str]:
    """Expand a 2-digit or 4-digit year string to 4-digit string.

    Rules:
        - 4-digit: returned as-is if in [2000, 2099].
        - 2-digit: '00'–'29' → '20YY', '30'–'99' → '19YY'.
        - Anything else → None.
    """
    if len(raw_yr) == 4:
        yr = int(raw_yr)
        return str(yr) if 2000 <= yr <= 2099 else None
    if len(raw_yr) == 2:
        yr = int(raw_yr)
        return f"20{raw_yr:>02}" if yr <= 29 else f"19{raw_yr:>02}"
    return None


# ---------------------------------------------------------------------------
# normalize_ticker
# ---------------------------------------------------------------------------
def normalize_ticker(raw: object) -> str:
    """Normalise an NSE ticker to stripped, uppercase canonical form.

    Rules (from Project Execution Plan §5.1):
        - Strip all leading/trailing whitespace.
        - Convert to UPPERCASE.
        - Internal hyphens and ampersands are preserved (e.g. 'BAJAJ-AUTO', 'M&M').
        - NaN / None / empty string → 'MISSING'.

    Returns:
        Uppercase stripped ticker string, or 'MISSING' if absent.
    """
    # pd.isna covers: None, float('nan'), pd.NA, pd.NaT
    try:
        if pd.isna(raw):  # type: ignore[arg-type]
            logger.debug("normalize_ticker received null → MISSING")
            return SENTINEL_MISSING
    except (TypeError, ValueError):
        pass  # non-scalar types handled below

    cleaned = str(raw).strip().upper()

    if not cleaned:
        return SENTINEL_MISSING

    return cleaned


# ---------------------------------------------------------------------------
# Series-level helpers (vectorised, for use inside DataLoader)
# ---------------------------------------------------------------------------
def normalize_ticker_series(series: pd.Series) -> pd.Series:
    """Apply normalize_ticker to an entire pandas Series (vectorised)."""
    return series.map(normalize_ticker)


def normalize_year_series(series: pd.Series) -> pd.Series:
    """Apply normalize_year to an entire pandas Series (vectorised)."""
    return series.map(normalize_year)
