"""
src/analytics/constants.py
--------------------------
Project-wide constants for the ratio and CAGR engines.

Single source of truth for all flag literals written to SQLite TEXT columns.
Import from here in cagr.py, ratio_engine.py, Day 12 population scripts,
and every test file — never define these strings inline.

Design principle: CagrFlag inherits from (str, Enum) so instances behave as
plain strings in SQLite inserts, f-strings, and logging without needing
.value everywhere. e.g. CagrFlag.TURNAROUND == "TURNAROUND" → True.
"""

from enum import Enum


class CagrFlag(str, Enum):
    """
    Canonical flag values stored in TEXT columns alongside CAGR results.
    Used for: revenue_cagr_5yr_flag, pat_cagr_5yr_flag, eps_cagr_5yr_flag,
    and the full 9-series in output/cagr_full.csv.

    Semantics:
    - INSUFFICIENT   : fewer years of data than the requested window
    - ZERO_BASE      : start value ≈ 0 (undefined growth denominator)
    - ZERO_END       : end value ≈ 0 (company at exact breakeven / zero profit)
    - DECLINE_TO_LOSS: positive start → negative end (profitable → loss)
    - TURNAROUND     : negative start → positive end (loss → profitable)
    - BOTH_NEGATIVE  : negative start AND negative end (persistent losses)

    Ordering note for calculate_cagr():
    ZERO_END is checked BEFORE TURNAROUND. Therefore start<0, end≈0 routes
    to ZERO_END (breakeven, not evaluated), not TURNAROUND.
    """

    INSUFFICIENT = "INSUFFICIENT"
    ZERO_BASE = "ZERO_BASE"
    ZERO_END = "ZERO_END"
    DECLINE_TO_LOSS = "DECLINE_TO_LOSS"
    TURNAROUND = "TURNAROUND"
    BOTH_NEGATIVE = "BOTH_NEGATIVE"


class FcfConversionFlag(str, Enum):
    ZERO_OP_PROFIT = "ZERO_OP_PROFIT"
    NEGATIVE_OP_PROFIT = "NEGATIVE_OP_PROFIT"
    NEGATIVE_FCF_POSITIVE_OP_PROFIT = "NEGATIVE_FCF_POSITIVE_OP_PROFIT"
    BOTH_NEGATIVE = "BOTH_NEGATIVE"


class CfoQualityLabel(str, Enum):
    HIGH_QUALITY = "High Quality"
    MODERATE = "Moderate"
    ACCRUAL_RISK = "Accrual Risk"


class CapexIntensityLabel(str, Enum):
    ASSET_LIGHT = "Asset Light"
    MODERATE = "Moderate"
    CAPITAL_INTENSIVE = "Capital Intensive"


class CashflowPatternLabel(str, Enum):
    REINVESTOR = "Reinvestor"
    SHAREHOLDER_RETURNS = "Shareholder Returns"
    LIQUIDATING_ASSETS = "Liquidating Assets"
    DISTRESS_SIGNAL = "Distress Signal"
    GROWTH_FUNDED_BY_DEBT = "Growth Funded by Debt"
    CASH_ACCUMULATOR = "Cash Accumulator"
    PRE_REVENUE = "Pre-Revenue"
    MIXED = "Mixed"
    UNCLASSIFIED = "Unclassified"


class CashflowPatternFlag(str, Enum):
    UNDEFINED_COMBINATION = "UNDEFINED_COMBINATION"


class CfoQualityScoreFlag(str, Enum):
    INSUFFICIENT_YEARS = "INSUFFICIENT_YEARS"
