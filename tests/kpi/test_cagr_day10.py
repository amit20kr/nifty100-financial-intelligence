"""
tests/kpi/test_cagr_day10.py
-----------------------------
Day 10 unit tests — CAGR Engine.

Tests 1-10:  Pure calculate_cagr() scalar tests — no I/O, hardcoded fixtures.
Tests 11-14: extract_cagr_window() tests — DataFrame fixtures mirroring real
             company shapes observed in the live DB audit:
             - ABB:     fiscal year-end Dec, has TTM row, gap at 2013
             - SIEMENS: fiscal year-end Sep, NO TTM row, gaps at 2012-2013

Imports CagrFlag from constants.py — never uses inline string literals.
"""

import pytest
import pandas as pd

from src.analytics.cagr import (
    calculate_cagr,
    extract_cagr_window,
)
from src.analytics.constants import CagrFlag


# ============================================================================
# Tests 1-10: calculate_cagr() — pure scalar tests
# ============================================================================


# Test 1: Normal growth — Pos → Pos, well above 1.0 CAGR
def test_cagr_normal_growth():
    """TCS-like revenue growth: 100 → 161.05 over 5yr ≈ 10.0% CAGR"""
    result = calculate_cagr(start_val=100.0, end_val=161.051, years=5)
    assert result.flag is None
    assert result.value is not None
    assert round(result.value, 2) == 10.0


# Test 2: Normal decline still positive — Pos → Pos, value < 0% CAGR
def test_cagr_normal_positive_decline():
    """Revenue fell from 200 to 150 over 5yr — still both positive, valid negative CAGR"""
    result = calculate_cagr(start_val=200.0, end_val=150.0, years=5)
    assert result.flag is None
    assert result.value is not None
    assert result.value < 0.0  # negative CAGR — shrinking but valid


# Test 3: Zero base — start_val exactly 0
def test_cagr_zero_base_exact():
    result = calculate_cagr(start_val=0.0, end_val=500.0, years=5)
    assert result.value is None
    assert result.flag == CagrFlag.ZERO_BASE


# Test 4: Zero end — end_val exactly 0 (company at breakeven)
def test_cagr_zero_end_exact():
    result = calculate_cagr(start_val=500.0, end_val=0.0, years=5)
    assert result.value is None
    assert result.flag == CagrFlag.ZERO_END


# Test 5: Decline to loss — Pos → Neg
def test_cagr_decline_to_loss():
    result = calculate_cagr(start_val=1000.0, end_val=-250.0, years=5)
    assert result.value is None
    assert result.flag == CagrFlag.DECLINE_TO_LOSS


# Test 6: Turnaround — Neg → Pos
def test_cagr_turnaround():
    result = calculate_cagr(start_val=-500.0, end_val=300.0, years=5)
    assert result.value is None
    assert result.flag == CagrFlag.TURNAROUND


# Test 7: Both negative — Neg → Neg
def test_cagr_both_negative():
    result = calculate_cagr(start_val=-200.0, end_val=-50.0, years=5)
    assert result.value is None
    assert result.flag == CagrFlag.BOTH_NEGATIVE


# Test 8: Insufficient data via flag
def test_cagr_insufficient_data_flag():
    result = calculate_cagr(
        start_val=100.0, end_val=200.0, years=10, insufficient_data=True
    )
    assert result.value is None
    assert result.flag == CagrFlag.INSUFFICIENT


# Test 9: years <= 0 guard — must raise ValueError, never ZeroDivisionError
def test_cagr_years_zero_raises():
    with pytest.raises(ValueError, match="years must be > 0"):
        calculate_cagr(start_val=100.0, end_val=200.0, years=0)


def test_cagr_years_negative_raises():
    with pytest.raises(ValueError, match="years must be > 0"):
        calculate_cagr(start_val=100.0, end_val=200.0, years=-3)


# Test 10: start<0, end≈0 — must route to ZERO_END (not TURNAROUND)
# This validates condition ordering: ZERO_END check is BEFORE TURNAROUND check.
def test_cagr_start_negative_end_zero_routes_to_zero_end():
    """
    Company climbing out of losses to exact breakeven EPS.
    start=-100 (loss), end=0 (breakeven).
    ZERO_END must fire before TURNAROUND because end_val is ≈ 0.
    """
    result = calculate_cagr(start_val=-100.0, end_val=0.0, years=5)
    assert result.value is None
    assert result.flag == CagrFlag.ZERO_END, (
        f"Expected ZERO_END, got {result.flag}. "
        "Check condition ordering: ZERO_END must precede TURNAROUND."
    )


# ============================================================================
# Tests 11-14: extract_cagr_window() — DataFrame fixture tests
# ============================================================================


def _make_series(rows: list[tuple]) -> pd.DataFrame:
    """Helper: build a mini P&L DataFrame with (year, sales, net_profit, eps) tuples."""
    return pd.DataFrame(rows, columns=["year", "sales", "net_profit", "eps"])


# ---------------------------------------------------------------------------
# ABB-like fixture: Dec fiscal year-end, HAS TTM row, gap at 2013
# Real series observed in live DB audit:
#   2012-12, [2013 ABSENT], 2014-03, 2015-03, ..., 2024-03, TTM
# ---------------------------------------------------------------------------
ABB_FIXTURE = _make_series(
    [
        ("2012-12", 1653.0, 145.0, 68.0),
        ("2014-03", 2276.0, 198.0, 93.0),
        ("2015-03", 2289.0, 229.0, 108.0),
        ("2016-03", 2614.0, 255.0, 120.0),
        ("2017-03", 2903.0, 277.0, 130.0),
        ("2018-03", 3298.0, 401.0, 189.0),
        ("2019-03", 3679.0, 450.0, 212.0),
        ("2020-03", 4093.0, 593.0, 279.0),
        ("2021-03", 4310.0, 691.0, 325.0),
        ("2022-03", 4913.0, 799.0, 376.0),
        ("2023-03", 5349.0, 949.0, 447.0),
        ("2024-03", 5849.0, 1201.0, 565.0),
        ("TTM", 6066.0, 1285.0, 605.0),  # ← must be excluded from window
    ]
)

# ---------------------------------------------------------------------------
# SIEMENS-like fixture: Sep fiscal year-end, NO TTM row, gaps at 2012-2013
# ---------------------------------------------------------------------------
SIEMENS_FIXTURE = _make_series(
    [
        ("2011-09", 11955.0, None, None),
        ("2014-09", 10678.0, None, None),
        ("2015-09", 10563.0, None, None),
        ("2016-09", 10837.0, None, None),
        ("2017-09", 11065.0, None, None),
        ("2018-09", 12795.0, None, None),
        ("2019-09", 13084.0, None, None),
        ("2020-09", 9946.0, None, None),
        ("2021-09", 13198.0, None, None),
        ("2022-09", 16138.0, None, None),
        ("2023-09", 19554.0, None, None),
        ("2024-09", 22240.0, None, None),
    ]
)


# Test 11: ABB — 5yr window, TTM excluded, correct start/end identified
def test_window_abb_5yr_ttm_excluded():
    """
    ABB 5yr revenue window: end_year=2024, start_year=2019.
    TTM row must be excluded — end_year must be 2024 (fiscal), not TTM.
    """
    start_val, end_val, actual_years, insufficient = extract_cagr_window(
        company_series=ABB_FIXTURE,
        window_years=5,
        metric_col="sales",
    )
    assert insufficient is False
    assert actual_years == 5
    # end_year=2024 → sales=5849; start_year=2019 → sales=3679
    assert end_val == pytest.approx(5849.0)
    assert start_val == pytest.approx(3679.0)


# Test 12: ABB — 10yr window, start_year=2014 (2013 absent but 2014 present)
def test_window_abb_10yr_sufficient():
    """
    ABB 10yr window: end_year=2024, start_year=2014.
    2013 is absent but 2014 is present — must compute normally.
    """
    start_val, end_val, actual_years, insufficient = extract_cagr_window(
        company_series=ABB_FIXTURE,
        window_years=10,
        metric_col="sales",
    )
    assert insufficient is False
    assert actual_years == 10
    assert end_val == pytest.approx(5849.0)  # 2024
    assert start_val == pytest.approx(2276.0)  # 2014


# Test 13: SIEMENS — 10yr window, start_year=2014 present → sufficient
#           SIEMENS — 13yr window, start_year=2011 present → sufficient
#           SIEMENS — 14yr window, start_year=2010 absent → INSUFFICIENT
def test_window_siemens_insufficient_when_start_absent():
    """
    SIEMENS has no 2012/2013 rows.
    12yr window: end=2024, start=2012 → absent → INSUFFICIENT.
    """
    start_val, end_val, actual_years, insufficient = extract_cagr_window(
        company_series=SIEMENS_FIXTURE,
        window_years=12,
        metric_col="sales",
    )
    assert insufficient is True
    assert start_val is None
    assert end_val is None


# Test 14: Two-company batch — TTM exclusion is targeted, not blanket
def test_window_ttm_exclusion_does_not_affect_non_ttm_company():
    """
    ABB (has TTM row) and SIEMENS (no TTM row) processed in same batch.
    ABB's TTM row must be filtered; SIEMENS's most recent row (2024-09)
    must be selected normally — targeted filter must not drop SIEMENS's last row.
    """
    # ABB: TTM excluded → end_year=2024, start_year=2019
    abb_start, abb_end, _, abb_insufficient = extract_cagr_window(
        ABB_FIXTURE, window_years=5, metric_col="sales"
    )
    # SIEMENS: no TTM row → end_year=2024, start_year=2019 → both present
    siem_start, siem_end, _, siem_insufficient = extract_cagr_window(
        SIEMENS_FIXTURE, window_years=5, metric_col="sales"
    )

    # ABB: TTM excluded correctly
    assert abb_insufficient is False
    assert abb_end == pytest.approx(5849.0)  # 2024-03, not TTM's 6066.0

    # SIEMENS: non-TTM company unaffected — 2019 and 2024 both present
    assert siem_insufficient is False
    assert siem_end == pytest.approx(22240.0)  # 2024-09
    assert siem_start == pytest.approx(13084.0)  # 2019-09
