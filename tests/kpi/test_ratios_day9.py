"""
tests/kpi/test_ratios_day9.py
------------------------------
Day 09 unit tests — Leverage & Efficiency Ratios.
All 8 formula tests use hardcoded fixtures (no live DB reads).

Test 9 (data_contract) is DB-touching: it asserts that FINANCIALS_SECTOR_LABEL
matches a real value in sectors.broad_sector. If someone renames the sector in
the data without updating the env var, this test fails CI loudly instead of
silently mis-tagging 23 companies.
"""

import os
import sqlite3
import pytest
from src.analytics.ratios import (
    FINANCIALS_SECTOR_LABEL,
    debt_to_equity,
    interest_coverage_ratio,
    net_debt,
    asset_turnover,
)

# ---------------------------------------------------------------------------
# Fixtures — TCS-like values for normal-case calculations
# Borrowings = 8021, Equity = 362, Reserves = 90127
# Operating Profit = 64296, Other Income = 3800, Interest = 778
# ---------------------------------------------------------------------------


# Test 1: D/E — debt-free company (borrowings == 0)
def test_de_debt_free():
    result = debt_to_equity(
        borrowings=0.0,
        equity_capital=362.0,
        reserves=90127.0,
        broad_sector="Technology",
    )
    assert result is not None
    assert result.value == 0.0
    assert result.high_leverage_flag is False


# Test 2: D/E — high leverage, non-Financials sector → flag raised
def test_de_high_leverage_non_financials():
    # D/E > 5: borrowings = 500000, equity+reserves = 90489 → D/E ≈ 5.53
    result = debt_to_equity(
        borrowings=500000.0,
        equity_capital=362.0,
        reserves=90127.0,
        broad_sector="Industrials",
    )
    assert result is not None
    assert result.value > 5.0
    assert result.high_leverage_flag is True


# Test 3: D/E — high leverage, Financials sector → flag suppressed
def test_de_high_leverage_financials_suppressed():
    result = debt_to_equity(
        borrowings=500000.0,
        equity_capital=362.0,
        reserves=90127.0,
        broad_sector=FINANCIALS_SECTOR_LABEL,  # "Financials" from env
    )
    assert result is not None
    assert result.value > 5.0
    assert (
        result.high_leverage_flag is None
    )  # suppressed — structurally normal for banks


# Test 4: ICR — interest == 0 (debt-free) → value=None, label="Debt Free", at_risk_flag=None
def test_icr_debt_free():
    result = interest_coverage_ratio(
        operating_profit=64296.0,
        other_income=3800.0,
        interest=0.0,
    )
    assert result.value is None
    assert result.label == "Debt Free"
    # at_risk_flag must be None (not False) — debt-free is "not evaluated", not "safe"
    assert result.at_risk_flag is None


# Test 5: ICR — normal case with interest > 0, ICR > 1.5 → not at risk
def test_icr_normal_not_at_risk():
    # ICR = (64296 + 3800) / 778 ≈ 87.52 → well above 1.5
    result = interest_coverage_ratio(
        operating_profit=64296.0,
        other_income=3800.0,
        interest=778.0,
    )
    assert result.value is not None
    assert round(result.value, 2) == 87.53
    assert result.label is None
    assert result.at_risk_flag is False


# Test 6: ICR — ICR < 1.5 → at_risk_flag=True
def test_icr_at_risk():
    # ICR = (500 + 100) / 1000 = 0.6 < 1.5 → at risk
    result = interest_coverage_ratio(
        operating_profit=500.0,
        other_income=100.0,
        interest=1000.0,
    )
    assert result.value is not None
    assert result.value == pytest.approx(0.6)
    assert result.at_risk_flag is True


# Test 7: Asset Turnover — total_assets == 0 → None
def test_asset_turnover_zero_assets():
    val = asset_turnover(sales=240893.0, total_assets=0.0)
    assert val is None


# Test 8: Net Debt — investments > borrowings → valid negative result (net cash position)
def test_net_debt_negative_is_valid():
    # Net cash: borrowings=8021, investments=50000 → net_debt = -41979
    result = net_debt(borrowings=8021.0, investments=50000.0)
    assert result is not None
    assert result < 0
    assert result == pytest.approx(-41979.0)


# ---------------------------------------------------------------------------
# Data Contract Test — DB-touching, validates FINANCIALS_SECTOR_LABEL
# ---------------------------------------------------------------------------


def test_financials_sector_label_in_db():
    """
    Assert that FINANCIALS_SECTOR_LABEL (from env) is a real value in
    sectors.broad_sector. Fails CI loudly if the sector is renamed in data
    without updating the env var — prevents silent mis-tagging of 23 companies.
    """
    db_path = os.getenv("DB_PATH", "db/nifty100.db")
    if not os.path.exists(db_path):
        pytest.skip(f"DB not found at {db_path} — skipping data contract test")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT broad_sector FROM sectors")
        distinct_sectors = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    assert FINANCIALS_SECTOR_LABEL in distinct_sectors, (
        f"FINANCIALS_SECTOR_LABEL='{FINANCIALS_SECTOR_LABEL}' not found in "
        f"sectors.broad_sector. Actual values: {sorted(distinct_sectors)}. "
        f"Update FINANCIALS_SECTOR_LABEL in .env to match the DB value."
    )
