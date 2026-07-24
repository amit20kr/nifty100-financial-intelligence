import math
from src.analytics.cashflow_kpis import (
    free_cash_flow,
    capex_intensity,
    fcf_conversion,
    cfo_quality_score,
    classify_cashflow_pattern,
    verify_capex_cross_check,
)
from src.analytics.constants import (
    FcfConversionFlag,
    CfoQualityLabel,
    CapexIntensityLabel,
    CashflowPatternLabel,
    CashflowPatternFlag,
    CfoQualityScoreFlag,
)


def test_1_fcf_normal():
    # Normal: CFO=+100, CFI=-40 -> fcf=60, capex=40
    res = free_cash_flow(100.0, -40.0)
    assert res.value == 60.0
    assert res.capex_cr == 40.0
    assert res.cfo_cr == 100.0


def test_2_fcf_cfi_positive():
    # CFI positive (asset sale) -> capex=0
    res = free_cash_flow(100.0, 20.0)
    assert res.value == 120.0
    assert res.capex_cr == 0.0


def test_3_fcf_cfo_negative():
    # CFO negative (cash burn) -> fcf negative
    res = free_cash_flow(-50.0, -20.0)
    assert res.value == -70.0
    assert res.capex_cr == 20.0


def test_4_fcf_nan_input():
    # NaN input -> value=None
    res = free_cash_flow(float("nan"), -40.0)
    assert res.value is None
    res = free_cash_flow(100.0, None)
    assert res.value is None


def test_5_capex_intensity_normal():
    # Normal -> value ≈ computed %
    res = capex_intensity(50.0, 1000.0)
    assert math.isclose(res.value, 5.0)
    assert res.label == CapexIntensityLabel.MODERATE.value


def test_6_capex_intensity_sales_zero():
    # sales=0 -> None
    res = capex_intensity(50.0, 0.0)
    assert res.value is None
    assert res.label is None


def test_7_fcf_conversion_normal():
    # Normal (FCF+, PAT+) -> value=computed, flag=None
    res = fcf_conversion(50.0, 100.0)
    assert math.isclose(res.value, 50.0)
    assert res.flag is None

    # Missing branch: FCF is None
    res2 = fcf_conversion(None, 100.0)
    assert res2.value is None

    # Missing branch: Both negative
    res3 = fcf_conversion(-50.0, -100.0)
    assert res3.flag == FcfConversionFlag.BOTH_NEGATIVE.value


def test_8_fcf_conversion_zero_op_profit():
    # operating_profit ≈ 0 -> None + ZERO_OP_PROFIT flag
    res = fcf_conversion(50.0, 0.0000001)
    assert res.value is None
    assert res.flag == FcfConversionFlag.ZERO_OP_PROFIT.value


def test_9_fcf_conversion_negative_op_profit():
    # operating_profit < 0 -> value=computed, flag=NEGATIVE_OP_PROFIT
    res = fcf_conversion(50.0, -100.0)
    assert math.isclose(res.value, -50.0)
    assert res.flag == FcfConversionFlag.NEGATIVE_OP_PROFIT.value


def test_10_fcf_conversion_negative_fcf_positive_op_profit():
    # FCF<0, OP_PROFIT>0 -> flag=NEGATIVE_FCF_POSITIVE_OP_PROFIT
    res = fcf_conversion(-20.0, 100.0)
    assert math.isclose(res.value, -20.0)
    assert res.flag == FcfConversionFlag.NEGATIVE_FCF_POSITIVE_OP_PROFIT.value


def test_11_classify_pattern_reinvestor(monkeypatch):
    monkeypatch.setenv("CFO_QUALITY_HIGH_THRESHOLD", "1.0")
    res = classify_cashflow_pattern(100.0, -50.0, -20.0, 0.8)
    assert res.pattern_code == "+--"
    assert res.pattern_label == CashflowPatternLabel.REINVESTOR.value


def test_12_classify_pattern_shareholder_returns(monkeypatch):
    monkeypatch.setenv("CFO_QUALITY_HIGH_THRESHOLD", "1.0")
    res = classify_cashflow_pattern(100.0, -50.0, -20.0, 1.2)
    assert res.pattern_code == "+--"
    assert res.pattern_label == CashflowPatternLabel.SHAREHOLDER_RETURNS.value


def test_13_classify_pattern_unclassified():
    res = classify_cashflow_pattern(-10.0, 20.0, -30.0, 0.5)
    assert res.pattern_code == "-+-"
    assert res.pattern_label == CashflowPatternLabel.UNCLASSIFIED.value
    assert res.pattern_flag == CashflowPatternFlag.UNDEFINED_COMBINATION.value

    # Check NaN inputs
    res_nan = classify_cashflow_pattern(float("nan"), 20.0, -30.0, 0.5)
    assert res_nan is None


def test_14_cfo_quality_score_insufficient_years():
    # exactly 2 of 5 valid years -> None + INSUFFICIENT_YEARS
    cfo_vals = [100.0, 120.0, None, float("nan"), 110.0]
    pat_vals = [50.0, 60.0, 70.0, 80.0, 0.0]
    res = cfo_quality_score(cfo_vals, pat_vals)
    assert res.value is None
    assert res.label is None
    assert res.flag == CfoQualityScoreFlag.INSUFFICIENT_YEARS.value

    # Valid score > 1.0 (High Quality)
    res_high = cfo_quality_score([110.0] * 5, [100.0] * 5)
    assert res_high.value == 1.1
    assert res_high.label == CfoQualityLabel.HIGH_QUALITY.value

    # Valid score 0.5 - 1.0 (Moderate)
    res_mod = cfo_quality_score([70.0] * 5, [100.0] * 5)
    assert math.isclose(res_mod.value, 0.7)
    assert res_mod.label == CfoQualityLabel.MODERATE.value

    # Valid score < 0.5 (Accrual Risk)
    res_risk = cfo_quality_score([30.0] * 5, [100.0] * 5)
    assert math.isclose(res_risk.value, 0.3)
    assert res_risk.label == CfoQualityLabel.ACCRUAL_RISK.value


def test_15_capex_intensity_boundaries():
    # boundaries: exactly 3%, exactly 8% -> inclusive/exclusive check
    # <3% Asset Light, <=8% Moderate, >8% Capital Intensive
    res1 = capex_intensity(3.0, 100.0)
    assert res1.label == CapexIntensityLabel.MODERATE.value

    res2 = capex_intensity(8.0, 100.0)
    assert res2.label == CapexIntensityLabel.MODERATE.value

    res3 = capex_intensity(8.001, 100.0)
    assert res3.label == CapexIntensityLabel.CAPITAL_INTENSIVE.value

    res4 = capex_intensity(2.99, 100.0)
    assert res4.label == CapexIntensityLabel.ASSET_LIGHT.value


def test_16_verify_capex_cross_check(monkeypatch):
    # Pre-seeded vs. computed capex_cr cross-check triggers a log entry when diff exceeds tolerance
    monkeypatch.setenv("CAPEX_CROSS_CHECK_TOLERANCE_PCT", "5.0")

    # Within tolerance
    assert verify_capex_cross_check(100.0, 102.0, "RELIANCE", 2023) is None

    # Exceeds tolerance
    msg = verify_capex_cross_check(110.0, 100.0, "RELIANCE", 2023)
    assert msg is not None
    assert "CAPEX MISMATCH [RELIANCE 2023]" in msg
    assert "Diff: 10.00%" in msg
