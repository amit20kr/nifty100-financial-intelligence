import os
import math
from typing import Optional, NamedTuple, List

from src.analytics.constants import (
    FcfConversionFlag,
    CfoQualityLabel,
    CapexIntensityLabel,
    CashflowPatternLabel,
    CashflowPatternFlag,
    CfoQualityScoreFlag,
)


class FcfResult(NamedTuple):
    value: Optional[float]
    capex_cr: Optional[float]
    cfo_cr: Optional[float]


class CapexIntensityResult(NamedTuple):
    value: Optional[float]
    label: Optional[str]


class FcfConversionResult(NamedTuple):
    value: Optional[float]
    flag: Optional[str]


class CfoQualityResult(NamedTuple):
    value: Optional[float]
    label: Optional[str]
    flag: Optional[str]


class CashflowPatternResult(NamedTuple):
    pattern_code: str
    pattern_label: str
    pattern_flag: Optional[str]
    cfo_sign: str
    cfi_sign: str
    cff_sign: str


def _get_epsilon() -> float:
    return float(os.getenv("CF_ZERO_EPSILON", "1e-6"))


def _get_cfo_high_threshold() -> float:
    return float(os.getenv("CFO_QUALITY_HIGH_THRESHOLD", "1.0"))


def free_cash_flow(
    operating_activity: Optional[float], investing_activity: Optional[float]
) -> FcfResult:
    if (
        operating_activity is None
        or investing_activity is None
        or math.isnan(operating_activity)
        or math.isnan(investing_activity)
    ):
        return FcfResult(None, None, operating_activity)

    fcf = operating_activity + investing_activity
    capex = abs(investing_activity) if investing_activity < 0 else 0.0

    return FcfResult(fcf, capex, operating_activity)


def capex_intensity(
    capex_cr: Optional[float], sales: Optional[float]
) -> CapexIntensityResult:
    if capex_cr is None or sales is None or math.isnan(capex_cr) or math.isnan(sales):
        return CapexIntensityResult(None, None)

    epsilon = _get_epsilon()
    if abs(sales) <= epsilon:
        return CapexIntensityResult(None, None)

    value = (capex_cr / sales) * 100.0

    label = None
    if value < 3.0:
        label = CapexIntensityLabel.ASSET_LIGHT.value
    elif value <= 8.0:
        label = CapexIntensityLabel.MODERATE.value
    else:
        label = CapexIntensityLabel.CAPITAL_INTENSIVE.value

    return CapexIntensityResult(value, label)


def fcf_conversion(
    fcf: Optional[float], operating_profit: Optional[float]
) -> FcfConversionResult:
    if (
        fcf is None
        or operating_profit is None
        or math.isnan(fcf)
        or math.isnan(operating_profit)
    ):
        return FcfConversionResult(None, None)

    epsilon = _get_epsilon()
    if abs(operating_profit) <= epsilon:
        return FcfConversionResult(None, FcfConversionFlag.ZERO_OP_PROFIT.value)

    value = (fcf / operating_profit) * 100.0

    flag = None
    if operating_profit < 0 and fcf < 0:
        flag = FcfConversionFlag.BOTH_NEGATIVE.value
    elif operating_profit < 0:
        flag = FcfConversionFlag.NEGATIVE_OP_PROFIT.value
    elif fcf < 0 and operating_profit > 0:
        flag = FcfConversionFlag.NEGATIVE_FCF_POSITIVE_OP_PROFIT.value

    return FcfConversionResult(value, flag)


def cfo_quality_score(
    cfo_values: List[Optional[float]], net_profit_values: List[Optional[float]]
) -> CfoQualityResult:
    valid_ratios = []
    epsilon = _get_epsilon()

    for cfo, pat in zip(cfo_values, net_profit_values):
        if (
            cfo is not None
            and pat is not None
            and not math.isnan(cfo)
            and not math.isnan(pat)
        ):
            if abs(pat) > epsilon:
                valid_ratios.append(cfo / pat)

    if len(valid_ratios) < 3:
        return CfoQualityResult(
            None, None, CfoQualityScoreFlag.INSUFFICIENT_YEARS.value
        )

    avg_score = sum(valid_ratios) / len(valid_ratios)

    label = None
    if avg_score > _get_cfo_high_threshold():
        label = CfoQualityLabel.HIGH_QUALITY.value
    elif avg_score >= 0.5:
        label = CfoQualityLabel.MODERATE.value
    else:
        label = CfoQualityLabel.ACCRUAL_RISK.value

    return CfoQualityResult(avg_score, label, None)


def _get_sign(val: float, epsilon: float) -> str:
    if val > epsilon:
        return "+"
    return "-"


def classify_cashflow_pattern(
    operating_activity: Optional[float],
    investing_activity: Optional[float],
    financing_activity: Optional[float],
    cfo_quality_ratio: Optional[float],
) -> Optional[CashflowPatternResult]:
    if (
        operating_activity is None
        or investing_activity is None
        or financing_activity is None
        or math.isnan(operating_activity)
        or math.isnan(investing_activity)
        or math.isnan(financing_activity)
    ):
        return None

    epsilon = _get_epsilon()
    cfo_sign = _get_sign(operating_activity, epsilon)
    cfi_sign = _get_sign(investing_activity, epsilon)
    cff_sign = _get_sign(financing_activity, epsilon)

    code = f"{cfo_sign}{cfi_sign}{cff_sign}"

    label = None
    flag = None

    if code == "+--":
        if (
            cfo_quality_ratio is not None
            and cfo_quality_ratio > _get_cfo_high_threshold()
        ):
            label = CashflowPatternLabel.SHAREHOLDER_RETURNS.value
        else:
            label = CashflowPatternLabel.REINVESTOR.value
    elif code == "++-":
        label = CashflowPatternLabel.LIQUIDATING_ASSETS.value
    elif code == "-++":
        label = CashflowPatternLabel.DISTRESS_SIGNAL.value
    elif code == "--+":
        label = CashflowPatternLabel.GROWTH_FUNDED_BY_DEBT.value
    elif code == "+++":
        label = CashflowPatternLabel.CASH_ACCUMULATOR.value
    elif code == "---":
        label = CashflowPatternLabel.PRE_REVENUE.value
    elif code == "+-+":
        label = CashflowPatternLabel.MIXED.value
    elif code == "-+-":
        label = CashflowPatternLabel.UNCLASSIFIED.value
        flag = CashflowPatternFlag.UNDEFINED_COMBINATION.value

    return CashflowPatternResult(code, label, flag, cfo_sign, cfi_sign, cff_sign)


def verify_capex_cross_check(
    computed_capex: float, pre_seeded_capex: float, company_name: str, year: int
) -> Optional[str]:
    """
    Cross-checks engine-computed capex against pre-seeded capex.
    Returns a log message string if diff > tolerance, else None.
    """
    if (
        computed_capex is None
        or pre_seeded_capex is None
        or math.isnan(computed_capex)
        or math.isnan(pre_seeded_capex)
    ):
        return None

    tolerance_pct = float(os.getenv("CAPEX_CROSS_CHECK_TOLERANCE_PCT", "5.0"))

    # If both are exactly 0, no diff
    if abs(pre_seeded_capex) <= 1e-6 and abs(computed_capex) <= 1e-6:
        return None

    # Prevent division by zero when calculating pct diff
    if abs(pre_seeded_capex) <= 1e-6:
        diff_pct = 100.0  # Or any arbitrarily large number since it's going from 0 to something
    else:
        diff_pct = abs((computed_capex - pre_seeded_capex) / pre_seeded_capex) * 100.0

    if diff_pct > tolerance_pct:
        return f"CAPEX MISMATCH [{company_name} {year}]: Computed {computed_capex} vs Pre-seeded {pre_seeded_capex} (Diff: {diff_pct:.2f}%)"

    return None
