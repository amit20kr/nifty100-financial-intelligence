"""
test_rules.py
=============
Test suite for DataValidator (Day 3 DQ Rules).
Validates that the 15 DQ rules correctly flag and coerce data.

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 3
"""

import pandas as pd
import pytest

from src.etl.normaliser import SENTINEL_PARSE_ERROR
from src.etl.validator import DataValidator


@pytest.fixture
def mock_frames() -> dict[str, pd.DataFrame]:
    """Provide a minimal clean state of frames for validation."""
    companies = pd.DataFrame(
        {
            "id": ["TCS", "HDFCBANK", "RELIANCE"],
            "company_name": ["Tata", "HDFC", "RIL"],
            "website": [
                "https://tcs.com",
                "http://hdfc.com",
                "https://www.reliance.com",
            ],
        }
    )

    balancesheet = pd.DataFrame(
        {
            "company_id": ["TCS", "HDFCBANK"],
            "year": ["2023-03", "2023-03"],
            "total_assets": [1000.0, 5000.0],
            "total_liabilities": [1000.0, 5000.0],
            "fixed_assets": [200.0, 100.0],
        }
    )

    profitandloss = pd.DataFrame(
        {
            "company_id": ["TCS", "HDFCBANK"],
            "year": ["2023-03", "2023-03"],
            "sales": [500.0, 2000.0],
            "operating_profit": [100.0, 400.0],
            "opm_percentage": [20.0, 20.0],
            "tax_percentage": [25.0, 25.0],
            "dividend_payout": [40.0, 40.0],
            "net_profit": [50.0, 200.0],
            "eps": [10.0, 50.0],
        }
    )

    cashflow = pd.DataFrame(
        {
            "company_id": ["TCS", "HDFCBANK"],
            "year": ["2023-03", "2023-03"],
            "operating_activity": [100.0, 400.0],
            "investing_activity": [-50.0, -100.0],
            "financing_activity": [-30.0, -50.0],
            "net_cash_flow": [20.0, 250.0],
        }
    )

    return {
        "companies": companies,
        "balancesheet": balancesheet,
        "profitandloss": profitandloss,
        "cashflow": cashflow,
    }


def test_validator_clean_state(mock_frames):
    """A clean dataset should produce zero failures."""
    v = DataValidator()
    # DQ-16 needs 5 years to pass, so let's mock it out for this simple test or add years
    # Actually, we can just check the failures list
    v.validate(mock_frames)

    # Only DQ-16 should trigger because we only provided 1 year of history
    failures = [f for f in v.failures if f.rule_id != "DQ-16"]
    assert len(failures) == 0, f"Unexpected failures: {failures}"


def test_dq02_composite_pk(mock_frames):
    """DQ-02: Duplicate (company_id, year) should halt execution."""
    mock_frames["profitandloss"].loc[2] = [
        "TCS",
        "2023-03",
        500.0,
        100.0,
        20.0,
        25.0,
        40.0,
        50.0,
        10.0,
    ]

    v = DataValidator()
    with pytest.raises(SystemExit):
        v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-02"]
    assert len(failures) == 2  # Both duplicate rows flagged


def test_dq03_orphan_drop(mock_frames):
    """DQ-03: Orphan rows should be dropped and logged."""
    mock_frames["profitandloss"].loc[2] = [
        "ORPHAN",
        "2023-03",
        500.0,
        100.0,
        20.0,
        25.0,
        40.0,
        50.0,
        10.0,
    ]

    v = DataValidator()
    out = v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-03"]
    assert len(failures) == 1
    assert failures[0].company_id == "ORPHAN"

    # Verify row was dropped
    assert "ORPHAN" not in out["profitandloss"]["company_id"].values


def test_dq04_balance_sheet_imbalance(mock_frames):
    """DQ-04: >1% imbalance should be flagged."""
    # TCS assets 1000, liab 1000. Change liab to 1020 (2% diff)
    mock_frames["balancesheet"].at[0, "total_liabilities"] = 1020.0

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-04"]
    assert len(failures) == 1
    assert failures[0].company_id == "TCS"


def test_dq05_opm_cross_check(mock_frames):
    """DQ-05: OPM mismatch > 1% should be flagged."""
    # TCS operating profit 100, sales 500 = 20%. Change opm_percentage to 25%.
    mock_frames["profitandloss"].at[0, "opm_percentage"] = 25.0

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-05"]
    assert len(failures) == 1
    assert failures[0].company_id == "TCS"


def test_dq06_positive_sales(mock_frames):
    """DQ-06: Sales <= 0 should be flagged."""
    mock_frames["profitandloss"].at[0, "sales"] = 0.0

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-06"]
    assert len(failures) == 1


def test_dq07_year_format_reject(mock_frames):
    """DQ-07: PARSE_ERROR year should be rejected."""
    mock_frames["profitandloss"].at[0, "year"] = SENTINEL_PARSE_ERROR

    v = DataValidator()
    out = v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-07"]
    assert len(failures) == 1
    assert len(out["profitandloss"]) == 1  # 1 row rejected


def test_dq08_ticker_format_reject(mock_frames):
    """DQ-08: MISSING or invalid ticker should be rejected."""
    # Add an invalid ticker 'X' (length 1) to companies so it bypasses DQ-03
    mock_frames["companies"].loc[3] = ["X", "Invalid", "http://x.com"]
    mock_frames["profitandloss"].loc[2] = [
        "X",
        "2023-03",
        500.0,
        100.0,
        20.0,
        25.0,
        40.0,
        50.0,
        10.0,
    ]

    v = DataValidator()
    out = v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-08"]
    assert len(failures) >= 1
    assert len(out["profitandloss"]) == 2  # 1 row rejected (from 3 total)


def test_dq09_net_cash_coercion(mock_frames):
    """DQ-09: Net cash mismatch > 10Cr should be flagged and coerced."""
    # TCS: CFO=100, CFI=-50, CFF=-30 -> sum = 20. Net cash set to 50.
    mock_frames["cashflow"].at[0, "net_cash_flow"] = 50.0

    v = DataValidator()
    out = v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-09"]
    assert len(failures) == 1

    # Verify coercion
    assert out["cashflow"].at[0, "net_cash_flow"] == 20.0


def test_dq10_fixed_assets_coercion(mock_frames):
    """DQ-10: Negative fixed assets coerced to 0."""
    mock_frames["balancesheet"].at[0, "fixed_assets"] = -10.0

    v = DataValidator()
    out = v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-10"]
    assert len(failures) == 1

    # Verify coercion
    assert out["balancesheet"].at[0, "fixed_assets"] == 0.0


def test_dq13_url_check(mock_frames):
    """DQ-13: Invalid URLs should be flagged."""
    # Inject an invalid URL
    mock_frames["companies"].at[2, "website"] = "www.reliance.com"
    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-13"]
    assert len(failures) == 1
    assert failures[0].company_id == "RELIANCE"


def test_dq14_eps_consistency(mock_frames):
    """DQ-14: Positive net profit but <=0 EPS should be flagged."""
    mock_frames["profitandloss"].at[0, "eps"] = -5.0

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-14"]
    assert len(failures) == 1


def test_dq01_duplicate_ticker_halts(mock_frames):
    """DQ-01: Duplicate tickers in the master companies list should halt execution."""
    mock_frames["companies"].loc[3] = ["TCS", "Tata Duplicate", "https://tcs.com"]

    v = DataValidator()
    with pytest.raises(SystemExit):
        v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-01"]
    assert len(failures) >= 1, "DQ-01 should log failures before halting"


def test_dq11_tax_rate_out_of_range(mock_frames):
    """DQ-11: Tax rate outside 0-60% should be flagged as WARNING."""
    # Set negative tax rate (loss year / deferred tax)
    mock_frames["profitandloss"].at[0, "tax_percentage"] = -25.0

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-11"]
    assert len(failures) == 1
    assert failures[0].company_id == "TCS"
    assert failures[0].severity == "WARNING"


def test_dq12_dividend_payout_cap(mock_frames):
    """DQ-12: Dividend payout > 200% should be flagged as WARNING."""
    mock_frames["profitandloss"].at[0, "dividend_payout"] = 250.0

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-12"]
    assert len(failures) == 1
    assert failures[0].company_id == "TCS"
    assert failures[0].severity == "WARNING"


def test_dq15_strict_balance_mismatch(mock_frames):
    """DQ-15: BSE strict balance check — any assets != liabilities triggers INFO."""
    mock_frames["balancesheet"].at[0, "total_liabilities"] = 1000.5  # 0.05% off

    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-15"]
    # DQ-15 is INFO, just verify it fires
    assert len(failures) == 1
    assert failures[0].severity == "INFO"


def test_dq16_coverage_check(mock_frames):
    """DQ-16: Companies with < 5 years of P&L should be flagged."""
    v = DataValidator()
    v.validate(mock_frames)

    failures = [f for f in v.failures if f.rule_id == "DQ-16"]
    # Our mock_frames only has 1 year per company, so both should be flagged
    assert len(failures) >= 1
    assert all(f.severity == "WARNING" for f in failures)
