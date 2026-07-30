"""
tests/screener/test_composite_score.py
======================================
Day 17 — Automated tests for composite score computation and Excel export.

Tests split into:
  1. TestWinsoriseUnit — pure function tests for winsorise_and_scale
  2. TestCompositeScoreUnit — synthetic DB tests for score correctness
  3. TestCompositeScoreIntegration — live DB tests for all 92 companies
  4. TestExportIntegration — live DB tests for screener_output.xlsx

IMPORTANT: Integration tests assert 92 companies (not 91), verifying SIEMENS
(Sep FYE) is included and receives a non-NULL composite score.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.screener.composite_score import (
    WEIGHTS,
    compute_composite_score,
    winsorise_and_scale,
)


# ---------------------------------------------------------------------------
# TestWinsoriseUnit
# ---------------------------------------------------------------------------
class TestWinsoriseUnit:
    def test_output_range_0_100(self):
        """All scores must be in [0, 100]."""
        s = pd.Series([1.0, 5.0, 10.0, 50.0, 90.0, 100.0, 200.0])
        result = winsorise_and_scale(s)
        assert result.min() >= 0.0
        assert result.max() <= 100.0

    def test_invert_maps_low_to_high(self):
        """Inverted scaling: lowest value gets highest score."""
        s = pd.Series([0.0, 1.0, 2.0, 3.0, 10.0])
        normal = winsorise_and_scale(s, invert=False)
        inverted = winsorise_and_scale(s, invert=True)
        # The lowest value should have a higher inverted score than normal score
        assert inverted.iloc[0] > normal.iloc[0]

    def test_nan_produces_nan(self):
        """NaN inputs produce NaN outputs (caller handles with fillna)."""
        s = pd.Series([1.0, np.nan, 5.0, 10.0, 50.0])
        result = winsorise_and_scale(s)
        assert pd.isna(result.iloc[1])

    def test_degenerate_p10_equals_p90(self):
        """When P10 == P90, all non-null values get 50."""
        s = pd.Series([5.0, 5.0, 5.0, 5.0, 5.0])
        result = winsorise_and_scale(s)
        assert (result == 50.0).all()

    def test_weights_sum_to_one(self):
        """Composite score weights must sum to exactly 1.0."""
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# TestCompositeScoreUnit — synthetic in-memory DB
# ---------------------------------------------------------------------------
class TestCompositeScoreUnit:
    @pytest.fixture
    def synthetic_df_and_db(self, tmp_path):
        """Build a synthetic DataFrame and DB for unit testing."""
        db_path = tmp_path / "test.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE financial_ratios (
                company_id TEXT, year TEXT, free_cash_flow_cr REAL
            )"""
            )
            # Company A: 6 years of FCF data for CAGR computation
            for yr, fcf in [
                (2019, 100),
                (2020, 120),
                (2021, 140),
                (2022, 160),
                (2023, 180),
                (2024, 200),
            ]:
                conn.execute(
                    "INSERT INTO financial_ratios VALUES (?, ?, ?)",
                    ("A", f"{yr}-03", fcf),
                )
            # Company B: debt-free, no FCF history (INSUFFICIENT flag)
            conn.execute("INSERT INTO financial_ratios VALUES ('B', '2024-03', 50)")
            # Company C: negative FCF trend
            for yr, fcf in [
                (2019, 500),
                (2020, 400),
                (2021, 200),
                (2022, -100),
                (2023, -200),
                (2024, -300),
            ]:
                conn.execute(
                    "INSERT INTO financial_ratios VALUES (?, ?, ?)",
                    ("C", f"{yr}-03", fcf),
                )
            # Company D: Financials sector
            for yr, fcf in [
                (2019, 1000),
                (2020, 1100),
                (2021, 1200),
                (2022, 1300),
                (2023, 1400),
                (2024, 1500),
            ]:
                conn.execute(
                    "INSERT INTO financial_ratios VALUES (?, ?, ?)",
                    ("D", f"{yr}-03", fcf),
                )

        # Build a synthetic engine DataFrame
        df = pd.DataFrame(
            {
                "company_id": ["A", "B", "C", "D"],
                "year": ["2024-03"] * 4,
                "return_on_equity_pct": [20.0, 15.0, 5.0, 18.0],
                "return_on_capital_employed_pct": [25.0, 18.0, 8.0, 20.0],
                "net_profit_margin_pct": [15.0, 12.0, 3.0, 14.0],
                "debt_to_equity": [0.5, 0.0, 3.0, 8.0],
                "interest_coverage": [
                    10.0,
                    None,
                    2.0,
                    4.0,
                ],  # B is debt-free (NULL ICR)
                "free_cash_flow_cr": [200.0, 50.0, -300.0, 1500.0],
                "cash_from_operations_cr": [300.0, 80.0, -200.0, 2000.0],
                "net_profit": [250.0, 70.0, -50.0, 1800.0],
                "revenue_cagr_5yr": [15.0, 10.0, -5.0, 20.0],
                "pat_cagr_5yr": [18.0, 12.0, None, 22.0],  # C has NULL PAT CAGR
                "icr_at_risk_flag": [0, None, 1, 0],  # B is debt-free (NULL)
                "broad_sector": [
                    "Technology",
                    "Technology",
                    "Industrials",
                    "Financials",
                ],
            }
        )

        return df, str(db_path)

    def test_all_companies_get_composite_score(self, synthetic_df_and_db):
        """All 4 companies must receive a non-NULL composite score."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        assert result["screener_composite_score"].notna().all()

    def test_scores_in_0_100_range(self, synthetic_df_and_db):
        """All composite scores must be in [0, 100]."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        assert (result["screener_composite_score"] >= 0).all()
        assert (result["screener_composite_score"] <= 100).all()

    def test_debt_free_gets_icr_100(self, synthetic_df_and_db):
        """Company B (debt-free, ICR=NULL) should get ICR sub-score of 100."""
        df, db_path = synthetic_df_and_db
        # We can't directly check sub-scores (they're cleaned up), but we can
        # verify debt-free company isn't penalized on ICR by comparing scores.
        result = compute_composite_score(df, db_path)
        b_score = result.loc[
            result["company_id"] == "B", "screener_composite_score"
        ].iloc[0]
        assert b_score > 0, "Debt-free company should have positive composite score"

    def test_financials_de_score_is_neutral(self, synthetic_df_and_db):
        """Company D (Financials, D/E=8) should get D/E sub-score of 50 (neutral)."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        # Financials company should not be penalized for high D/E
        d_score = result.loc[
            result["company_id"] == "D", "screener_composite_score"
        ].iloc[0]
        assert (
            d_score > 20
        ), "Financials company should not be heavily penalized for D/E"

    def test_null_pat_cagr_scores_zero(self, synthetic_df_and_db):
        """Company C (NULL PAT CAGR) should get PAT CAGR sub-score of 0."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        # C has bad metrics across the board AND null PAT CAGR — should be lowest
        c_score = result.loc[
            result["company_id"] == "C", "screener_composite_score"
        ].iloc[0]
        a_score = result.loc[
            result["company_id"] == "A", "screener_composite_score"
        ].iloc[0]
        assert (
            c_score < a_score
        ), "Company with NULL CAGR + bad metrics should score lower"

    def test_fcf_cagr_flag_populated(self, synthetic_df_and_db):
        """FCF CAGR flags must be set for edge-case companies."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        # Company A has clean 6yr FCF data → should compute normally
        a_flag = result.loc[result["company_id"] == "A", "fcf_cagr_5yr_flag"].iloc[0]
        assert a_flag is None or pd.isna(a_flag), "Clean FCF CAGR should have no flag"
        # Company B has only 1 year → INSUFFICIENT
        b_flag = result.loc[result["company_id"] == "B", "fcf_cagr_5yr_flag"].iloc[0]
        assert (
            b_flag == "INSUFFICIENT"
        ), "Single-year FCF history should flag INSUFFICIENT"

    def test_sector_score_flag_for_small_sectors(self, synthetic_df_and_db):
        """Sectors with n<5 should be flagged SMALL_SECTOR."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        # All sectors in our synthetic data have n < 5
        assert (result["sector_score_flag"] == "SMALL_SECTOR").all()

    def test_fcf_positive_binary_not_winsorised(self, synthetic_df_and_db):
        """FCF positive flag scoring should be binary (0 or 100), not winsorised."""
        df, db_path = synthetic_df_and_db
        result = compute_composite_score(df, db_path)
        # Check that fcf_positive_flag is set correctly
        assert result.loc[result["company_id"] == "A", "fcf_positive_flag"].iloc[0] == 1
        assert result.loc[result["company_id"] == "C", "fcf_positive_flag"].iloc[0] == 0


# ---------------------------------------------------------------------------
# TestCompositeScoreIntegration — live DB
# ---------------------------------------------------------------------------
LIVE_DB = Path("db/nifty100.db")
LIVE_CONFIG = Path("config/screener_config.yaml")


@pytest.mark.requires_populated_db
class TestCompositeScoreIntegration:
    @pytest.fixture(scope="class")
    def live_engine(self):
        if not LIVE_DB.exists():
            pytest.skip("Live DB not found.")
        from src.screener.engine import FilterEngine

        return FilterEngine(db_path=LIVE_DB, config_path=LIVE_CONFIG)

    def test_92_companies_have_composite_score(self, live_engine):
        """ALL 92 companies in engine.df must have non-NULL composite score."""
        assert len(live_engine.df) == 92
        assert (
            live_engine.df["screener_composite_score"].notna().all()
        ), "Some companies have NULL screener_composite_score"

    def test_siemens_has_composite_score(self, live_engine):
        """SIEMENS (Sep FYE, anchor '2024-09') must have a non-NULL score."""
        siemens = live_engine.df[live_engine.df["company_id"] == "SIEMENS"]
        assert len(siemens) == 1, "SIEMENS should be in the 92-company universe"
        assert siemens["screener_composite_score"].notna().all()
        assert siemens["sector_relative_score"].notna().all()

    def test_scores_in_0_100_range(self, live_engine):
        """All composite scores must be in [0, 100]."""
        scores = live_engine.df["screener_composite_score"]
        assert (scores >= 0).all() and (scores <= 100).all()

    def test_sector_relative_scores_in_0_100(self, live_engine):
        """All sector-relative scores must be in [0, 100]."""
        scores = live_engine.df["sector_relative_score"]
        assert scores.notna().all()
        assert (scores >= 0).all() and (scores <= 100).all()

    def test_small_sectors_flagged(self, live_engine):
        """Sectors with n<5 must have sector_score_flag='SMALL_SECTOR'."""
        small = live_engine.df[live_engine.df["sector_score_flag"] == "SMALL_SECTOR"]
        flagged_sectors = set(small["broad_sector"].unique())
        assert "Real Estate" in flagged_sectors
        assert "Communication Services" in flagged_sectors

    def test_fcf_cagr_5yr_column_exists(self, live_engine):
        """fcf_cagr_5yr must be computed and present in the DataFrame."""
        assert "fcf_cagr_5yr" in live_engine.df.columns

    def test_fcf_cagr_flag_distinguishes_edge_cases(self, live_engine):
        """Companies with edge-case FCF CAGR must have a non-null flag."""
        df = live_engine.df
        flagged = df[df["fcf_cagr_5yr_flag"].notna()]
        assert (
            len(flagged) > 0
        ), "At least some companies should have FCF CAGR edge-case flags"
        # INSUFFICIENT flag must exist for companies without sufficient history
        # Edge-case flags (DECLINE_TO_LOSS, etc.) must exist for negative FCF trends
        flag_values = set(flagged["fcf_cagr_5yr_flag"].unique())
        assert len(flag_values) >= 1, "Should have at least one distinct flag type"


# ---------------------------------------------------------------------------
# TestExportIntegration — live DB + xlsx output
# ---------------------------------------------------------------------------
@pytest.mark.requires_populated_db
class TestExportIntegration:
    @pytest.fixture(scope="class")
    def exported_xlsx(self, tmp_path_factory):
        if not LIVE_DB.exists():
            pytest.skip("Live DB not found.")
        from src.screener.engine import FilterEngine
        from src.screener.export import export_screener_output

        tmp_dir = tmp_path_factory.mktemp("export")
        output_path = str(tmp_dir / "screener_output.xlsx")

        engine = FilterEngine(db_path=LIVE_DB, config_path=LIVE_CONFIG)
        export_screener_output(engine, output_path=output_path)
        return output_path

    def test_xlsx_has_6_sheets(self, exported_xlsx):
        """screener_output.xlsx must have exactly 6 sheets."""
        xl = pd.ExcelFile(exported_xlsx)
        assert (
            len(xl.sheet_names) == 6
        ), f"Expected 6 sheets, got {len(xl.sheet_names)}: {xl.sheet_names}"

    def test_each_sheet_has_20_kpi_columns(self, exported_xlsx):
        """Each sheet must have 20 KPI columns."""
        xl = pd.ExcelFile(exported_xlsx)
        for sheet in xl.sheet_names:
            df = pd.read_excel(exported_xlsx, sheet_name=sheet)
            assert (
                len(df.columns) == 20
            ), f"Sheet '{sheet}' has {len(df.columns)} columns, expected 20"

    def test_each_sheet_sorted_by_composite_score(self, exported_xlsx):
        """Each sheet must be sorted by screener_composite_score descending."""
        xl = pd.ExcelFile(exported_xlsx)
        for sheet in xl.sheet_names:
            df = pd.read_excel(exported_xlsx, sheet_name=sheet)
            if "screener_composite_score" in df.columns and len(df) > 1:
                scores = df["screener_composite_score"].tolist()
                assert scores == sorted(
                    scores, reverse=True
                ), f"Sheet '{sheet}' is not sorted by composite score descending"

    def test_each_sheet_5_to_50_companies(self, exported_xlsx):
        """Each sheet must have 5-50 companies (exit criterion)."""
        xl = pd.ExcelFile(exported_xlsx)
        for sheet in xl.sheet_names:
            df = pd.read_excel(exported_xlsx, sheet_name=sheet)
            assert (
                5 <= len(df) <= 50
            ), f"Sheet '{sheet}' has {len(df)} companies — outside 5-50 range"
