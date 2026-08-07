from src.analytics.cashflow_kpis import (
    capex_intensity,
    cfo_quality_score,
    classify_cashflow_pattern,
    check_distress_signal,
    check_deleveraging,
)
from src.analytics.constants import (
    CapexIntensityLabel,
    CfoQualityLabel,
    CfoQualityScoreFlag,
    CashflowPatternLabel,
)


def test_capex_intensity():
    # Asset Light (< 3%)
    res1 = capex_intensity(2.0, 100.0)
    assert res1.value == 2.0
    assert res1.label == CapexIntensityLabel.ASSET_LIGHT.value

    # Moderate (3 - 8%)
    res2 = capex_intensity(5.0, 100.0)
    assert res2.value == 5.0
    assert res2.label == CapexIntensityLabel.MODERATE.value

    # Capital Intensive (> 8%)
    res3 = capex_intensity(10.0, 100.0)
    assert res3.value == 10.0
    assert res3.label == CapexIntensityLabel.CAPITAL_INTENSIVE.value

    # Edge cases
    assert capex_intensity(None, 100.0).value is None
    assert capex_intensity(10.0, 0.0).value is None


def test_cfo_quality_score():
    # Needs at least 3 valid years
    res = cfo_quality_score([100.0, 120.0], [50.0, 60.0])
    assert res.value is None
    assert res.flag == CfoQualityScoreFlag.INSUFFICIENT_YEARS.value

    # High Quality (> 1.0)
    cfo_vals = [120.0, 130.0, 110.0, 140.0, 150.0]
    pat_vals = [100.0, 100.0, 100.0, 100.0, 100.0]
    res2 = cfo_quality_score(cfo_vals, pat_vals)
    assert res2.value > 1.0
    assert res2.label == CfoQualityLabel.HIGH_QUALITY.value


def test_classify_cashflow_pattern():
    # Shareholder returns: +-- with high cfo quality (>1.0)
    res = classify_cashflow_pattern(100.0, -50.0, -20.0, 1.5)
    assert res.pattern_code == "+--"
    assert res.pattern_label == CashflowPatternLabel.SHAREHOLDER_RETURNS.value

    # Reinvestor: +-- with low cfo quality (<1.0)
    res = classify_cashflow_pattern(100.0, -50.0, -20.0, 0.8)
    assert res.pattern_label == CashflowPatternLabel.REINVESTOR.value

    # Distress signal: -++
    res = classify_cashflow_pattern(-10.0, 50.0, 20.0, 0.5)
    assert res.pattern_code == "-++"
    assert res.pattern_label == CashflowPatternLabel.DISTRESS_SIGNAL.value


def test_check_distress_signal():
    # True if CFO < 0 and CFF > 0
    assert check_distress_signal(-10.0, 50.0) is True
    # False if CFO > 0
    assert check_distress_signal(10.0, 50.0) is False
    # False if CFF < 0
    assert check_distress_signal(-10.0, -50.0) is False
    # Missing data
    assert check_distress_signal(None, 50.0) is False


def test_check_deleveraging():
    # True if CFF < 0 and current_borrowing < prev_borrowing
    assert check_deleveraging(-50.0, 200.0, 150.0) is True
    # False if CFF > 0
    assert check_deleveraging(50.0, 200.0, 150.0) is False
    # False if borrowing increases
    assert check_deleveraging(-50.0, 150.0, 200.0) is False
    # False if debt-free in both periods (0 < 0 is False)
    assert check_deleveraging(-50.0, 0.0, 0.0) is False
    # Missing prior year
    assert check_deleveraging(-50.0, None, 150.0) is None
    # Missing CFF
    assert check_deleveraging(None, 200.0, 150.0) is False
