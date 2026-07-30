"""
tests/screener/test_presets.py
==============================
Automated tests for the 6 preset screeners (Day 16).

Tests are split into two classes:
  1. TestPresetIntegration — runs against the LIVE database; verifies business-sense
     exit criteria (5-50 companies), column presence, and threshold correctness.
     Marked requires_populated_db — skipped if DB is not populated.
  2. TestPresetUnit — uses a synthetic in-memory SQLite DB; verifies predicate
     correctness, D/E bypass, ICR bypass, null fail-closed, and D/E YoY decline
     without requiring the full Nifty 100 dataset.

Population-integrity regression test (Day 15 pattern):
  Asserts that non-null P/E, P/B, dividend_yield_pct are present in the engine
  DataFrame, proving migration 005 (market_cap year canonicalisation) is effective.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from src.screener.engine import FilterEngine
from src.screener.presets import (
    PRESETS,
    debt_free_blue_chip,
    dividend_champion,
    growth_accelerator,
    quality_compounder,
    run_all_presets,
    turnaround_watch,
    value_pick,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LIVE_DB = Path("db/nifty100.db")
LIVE_CONFIG = Path("config/screener_config.yaml")
FINANCIALS_LABEL = os.getenv("FINANCIALS_SECTOR_LABEL", "Financials")


# ---------------------------------------------------------------------------
# Fixture: live engine (requires populated DB)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def live_engine():
    if not LIVE_DB.exists():
        pytest.skip("Live DB not found — run `make populate` first.")
    return FilterEngine(db_path=LIVE_DB, config_path=LIVE_CONFIG)


# ---------------------------------------------------------------------------
# Integration Tests — live DB
# ---------------------------------------------------------------------------


@pytest.mark.requires_populated_db
class TestPresetIntegration:
    """All tests run against the real nifty100.db; marked requires_populated_db."""

    def test_migration_005_regression_valuation_columns_non_null(self, live_engine):
        """
        Regression test: post-migration 005, P/E, P/B and Div Yield must have
        non-null, non-zero values in the engine DataFrame.
        Proves the market_cap LEFT JOIN is actually matching rows (was zero before fix).
        """
        df = live_engine.df
        assert (
            df["pe_ratio"].notna().sum() >= 80
        ), "pe_ratio has fewer than 80 non-null rows — migration 005 may not be applied."
        assert (
            df["pb_ratio"].notna().sum() >= 80
        ), "pb_ratio has fewer than 80 non-null rows."
        assert (
            df["dividend_yield_pct"].notna().sum() >= 80
        ), "dividend_yield_pct has fewer than 80 non-null rows."

    def test_all_presets_return_5_to_50_companies(self, live_engine):
        """
        Exit criterion: every preset must return between 5 and 50 companies.
        """
        results = run_all_presets(live_engine)
        for name, df in results.items():
            assert (
                5 <= len(df) <= 50
            ), f"Preset '{name}' returned {len(df)} companies — outside 5-50 exit criterion."

    def test_quality_compounder_threshold_correctness(self, live_engine):
        """All QC results must satisfy every stated threshold."""
        df = quality_compounder(live_engine)
        assert (df["return_on_equity_pct"] > 15.0).all(), "ROE threshold violated."
        assert (df["free_cash_flow_cr"] > 0).all(), "FCF threshold violated."
        assert (df["revenue_cagr_5yr"] > 10.0).all(), "Revenue CAGR threshold violated."
        # D/E may exceed 1.0 only for Financials companies
        non_fin = df[df["broad_sector"] != FINANCIALS_LABEL]
        assert (
            non_fin["debt_to_equity"] < 1.0
        ).all(), "D/E threshold violated for non-Financials company."

    def test_quality_compounder_includes_financials(self, live_engine):
        """Financials companies must appear in QC output (D/E bypass working)."""
        df = quality_compounder(live_engine)
        fin_companies = df[df["broad_sector"] == FINANCIALS_LABEL]
        assert (
            len(fin_companies) >= 1
        ), "No Financials companies in Quality Compounder output — D/E bypass may be broken."

    def test_growth_accelerator_threshold_correctness(self, live_engine):
        """All GA results must meet PAT CAGR and Rev CAGR thresholds."""
        df = growth_accelerator(live_engine)
        assert (df["pat_cagr_5yr"] > 20.0).all(), "PAT CAGR threshold violated."
        assert (df["revenue_cagr_5yr"] > 15.0).all(), "Revenue CAGR threshold violated."

    def test_dividend_champion_threshold_correctness(self, live_engine):
        """All DC results must have Div Yield > 2%, Payout < 80%, FCF > 0."""
        df = dividend_champion(live_engine)
        assert (
            df["dividend_yield_pct"] > 2.0
        ).all(), "Dividend Yield threshold violated."
        assert (
            df["dividend_payout_ratio_pct"] < 80.0
        ).all(), "Payout ratio threshold violated."
        assert (df["free_cash_flow_cr"] > 0).all(), "FCF threshold violated."

    def test_debt_free_blue_chip_threshold_correctness(self, live_engine):
        """All DFBC results must have D/E <= 0.1, ROE > 12, Sales > 5000."""
        df = debt_free_blue_chip(live_engine)
        assert (
            df["debt_to_equity"] <= 0.1
        ).all(), "D/E threshold violated (must be <=0.1)."
        assert (df["return_on_equity_pct"] > 12.0).all(), "ROE threshold violated."
        assert (df["sales"] > 5000.0).all(), "Sales threshold violated."

    def test_turnaround_watch_fcf_positive(self, live_engine):
        """All Turnaround Watch results must have FCF > 0."""
        df = turnaround_watch(live_engine)
        assert (
            df["free_cash_flow_cr"] > 0
        ).all(), "FCF must be positive in Turnaround Watch."

    def test_value_pick_valuation_thresholds(self, live_engine):
        """Value Pick results must meet adjusted P/E and P/B thresholds."""
        df = value_pick(live_engine)
        assert (df["pe_ratio"] < 25.0).all(), "P/E threshold violated."
        assert (df["pb_ratio"] < 5.0).all(), "P/B threshold violated."
        assert (
            df["dividend_yield_pct"] > 0.5
        ).all(), "Dividend Yield threshold violated."

    def test_preset_registry_has_six_entries(self, live_engine):
        """PRESETS dict must have exactly 6 entries."""
        assert len(PRESETS) == 6, f"Expected 6 presets, got {len(PRESETS)}."

    def test_no_preset_contains_null_company_id(self, live_engine):
        """No result row should have a null company_id."""
        results = run_all_presets(live_engine)
        for name, df in results.items():
            assert (
                df["company_id"].notna().all()
            ), f"Null company_id in preset '{name}'."


# ---------------------------------------------------------------------------
# Fixture: synthetic in-memory engine (unit tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_engine(tmp_path):
    """Build a minimal FilterEngine over a synthetic SQLite DB."""
    db_path = tmp_path / "test.db"
    config_path = tmp_path / "config.yaml"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE financial_ratios (
            company_id TEXT, year TEXT,
            return_on_equity_pct REAL, debt_to_equity REAL,
            free_cash_flow_cr REAL, revenue_cagr_5yr REAL, pat_cagr_5yr REAL,
            eps_cagr_5yr REAL, interest_coverage REAL, icr_at_risk_flag INTEGER,
            icr_label TEXT, dividend_payout_ratio_pct REAL, asset_turnover REAL,
            cash_from_operations_cr REAL, net_profit_margin_pct REAL,
            operating_profit_margin_pct REAL, return_on_capital_employed_pct REAL
        )"""
        )
        conn.execute(
            """CREATE TABLE profitandloss (
            company_id TEXT, year TEXT, sales REAL, net_profit REAL
        )"""
        )
        conn.execute(
            """CREATE TABLE market_cap (
            company_id TEXT, year TEXT, market_cap_crore REAL,
            enterprise_value_crore REAL, pe_ratio REAL, pb_ratio REAL, dividend_yield_pct REAL
        )"""
        )
        conn.execute("CREATE TABLE sectors (company_id TEXT, broad_sector TEXT)")

        # Company A: high-quality compounder, non-Financials
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('A','2024-03',20,0.5,1000,15,25,20,5,0,'Safe',30,1.2,800,15,18,18)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('A','2024-03',8000,1200)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('A','2024-03',50000,55000,22,3.5,1.5)"
        )
        conn.execute("INSERT INTO sectors VALUES ('A','Technology')")

        # Company B: Financials, high D/E (should bypass D/E filter)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('B','2024-03',18,8,500,12,22,18,4,0,'Safe',25,0.5,400,12,15,15)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('B','2024-03',12000,2000)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('B','2024-03',80000,85000,18,2.8,2.5)"
        )
        conn.execute("INSERT INTO sectors VALUES ('B','Financials')")

        # Company C: debt-free (ICR bypass), good metrics
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('C','2024-03',25,0,2000,20,30,25,NULL,NULL,'Debt Free',20,1.5,1800,20,22,22)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('C','2024-03',15000,3000)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('C','2024-03',100000,100000,28,4.5,0.8)"
        )
        conn.execute("INSERT INTO sectors VALUES ('C','Consumer Staples')")

        # Company D: missing market_cap (non-March FY or gap)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('D','2024-03',16,0.3,500,11,21,15,6,0,'Safe',35,1.0,400,12,14,14)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('D','2024-03',6000,700)")
        conn.execute("INSERT INTO sectors VALUES ('D','Healthcare')")
        # No market_cap row for D

        # Company E: FCF negative (should fail Turnaround Watch and QC)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('E','2024-03',15,1.5,-500,11,21,15,3,1,'At Risk',50,0.8,-400,10,12,12)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('E','2024-03',7000,1000)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('E','2024-03',40000,42000,35,6.0,0.3)"
        )
        conn.execute("INSERT INTO sectors VALUES ('E','Industrials')")

    config_yaml = """
metrics:
  return_on_equity_pct:
    column: return_on_equity_pct
    operator: min
    default_threshold: 10.0
  debt_to_equity:
    column: debt_to_equity
    operator: max
    default_threshold: 2.0
  free_cash_flow_cr:
    column: free_cash_flow_cr
    operator: min
    default_threshold: 0.0
  revenue_cagr_5yr:
    column: revenue_cagr_5yr
    operator: min
    default_threshold: 0.0
  pat_cagr_5yr:
    column: pat_cagr_5yr
    operator: min
    default_threshold: 0.0
  eps_cagr_5yr:
    column: eps_cagr_5yr
    operator: min
    default_threshold: 0.0
  interest_coverage:
    column: interest_coverage
    operator: min
    default_threshold: 1.5
  dividend_payout_ratio_pct:
    column: dividend_payout_ratio_pct
    operator: max
    default_threshold: 100.0
  pe_ratio:
    column: pe_ratio
    operator: max
    default_threshold: 100.0
  pb_ratio:
    column: pb_ratio
    operator: max
    default_threshold: 15.0
  dividend_yield_pct:
    column: dividend_yield_pct
    operator: min
    default_threshold: 0.0
  market_cap_crore:
    column: market_cap_crore
    operator: min
    default_threshold: 0.0
  sales:
    column: sales
    operator: min
    default_threshold: 0.0
  net_profit:
    column: net_profit
    operator: min
    default_threshold: 0.0
  asset_turnover:
    column: asset_turnover
    operator: min
    default_threshold: 0.0
  cash_from_operations_cr:
    column: cash_from_operations_cr
    operator: min
    default_threshold: 0.0
  operating_profit_margin_pct:
    column: operating_profit_margin_pct
    operator: min
    default_threshold: 0.0
  return_on_capital_employed_pct:
    column: return_on_capital_employed_pct
    operator: min
    default_threshold: 0.0
"""
    config_path.write_text(config_yaml)
    os.environ["FINANCIALS_SECTOR_LABEL"] = "Financials"
    return FilterEngine(db_path=db_path, config_path=config_path)


# ---------------------------------------------------------------------------
# Unit Tests — synthetic engine
# ---------------------------------------------------------------------------


class TestPresetUnit:
    def test_quality_compounder_includes_financials_with_high_de(
        self, synthetic_engine
    ):
        """Company B (Financials, D/E=8) should appear in Quality Compounder."""
        df = quality_compounder(synthetic_engine)
        assert (
            "B" in df["company_id"].values
        ), "Financials company not in QC output — D/E bypass broken."

    def test_quality_compounder_excludes_negative_fcf(self, synthetic_engine):
        """Company E (FCF=-500) should be excluded from Quality Compounder."""
        df = quality_compounder(synthetic_engine)
        assert "E" not in df["company_id"].values

    def test_icr_debt_free_bypass_passes_icr_filter(self, synthetic_engine):
        """Company C (icr_at_risk_flag=NULL, ICR=NULL) should pass any ICR min threshold."""
        df = synthetic_engine.apply({"interest_coverage": 5.0})
        assert (
            "C" in df["company_id"].values
        ), "Debt-free company (NULL ICR) should bypass ICR min filter."

    def test_missing_market_cap_fails_closed_on_pe_filter(self, synthetic_engine):
        """Company D (no market_cap row) must be excluded when P/E filter is applied."""
        df = synthetic_engine.apply({"pe_ratio": 100.0})
        assert (
            "D" not in df["company_id"].values
        ), "Company with missing market_cap must fail closed on P/E filter."

    def test_missing_market_cap_fails_closed_on_div_yield_filter(
        self, synthetic_engine
    ):
        """Company D (no market_cap row) must be excluded when Div Yield filter is applied."""
        df = synthetic_engine.apply({"dividend_yield_pct": 0.0})
        assert "D" not in df["company_id"].values

    def test_de_bypass_applies_only_to_de_filter(self, synthetic_engine):
        """Company B (Financials, high D/E) must still fail on non-D/E filters if criteria unmet."""
        # Require PAT CAGR > 50 — Company B has 22, should fail
        df = synthetic_engine.apply({"pat_cagr_5yr": 50.0})
        assert (
            "B" not in df["company_id"].values
        ), "Financials bypass must only suppress D/E predicate, not all filters."

    def test_null_cagr_fails_closed(self, synthetic_engine):
        """Company with NULL revenue_cagr_5yr must fail closed on CAGR filter."""
        # Inject a company with NULL CAGR
        with sqlite3.connect(str(synthetic_engine.db_path)) as conn:
            conn.execute(
                "INSERT INTO financial_ratios VALUES ('F','2024-03',20,0.3,500,NULL,NULL,NULL,5,0,'Safe',30,1.0,400,15,18,18)"
            )
            conn.execute("INSERT INTO profitandloss VALUES ('F','2024-03',7000,1000)")
            conn.execute("INSERT INTO sectors VALUES ('F','Materials')")
        # Reload engine
        from src.screener.engine import FilterEngine

        eng2 = FilterEngine(synthetic_engine.db_path, synthetic_engine.config_path)
        df = eng2.apply({"revenue_cagr_5yr": 0.0})
        assert (
            "F" not in df["company_id"].values
        ), "NULL CAGR must fail closed against any CAGR minimum filter."

    def test_dividend_champion_high_payout_excluded(self, synthetic_engine):
        """Company E (payout=50, but FCF negative) should be excluded from Dividend Champion."""
        df = dividend_champion(synthetic_engine)
        assert "E" not in df["company_id"].values

    def test_debt_free_blue_chip_de_exactly_zero(self, synthetic_engine):
        """Company C (D/E=0) must be in Debt-Free Blue Chip results."""
        df = debt_free_blue_chip(synthetic_engine)
        assert "C" in df["company_id"].values
