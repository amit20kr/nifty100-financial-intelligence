"""
tests/nlp/test_parser.py
------------------------
Mandatory test suite for src/nlp/parser.py — Day 29.

Covers:
    parse_analysis_text()    — 12 cases including all format variations observed in DB sample
    parse_analysis_table()   — integration against in-memory DataFrames
    cross_validate_cagr()    — divergence computation, NULL handling, flag boundary
"""

import pandas as pd

from src.nlp.parser import (
    parse_analysis_text,
    parse_analysis_table,
    cross_validate_cagr,
    METRIC_SALES_GROWTH,
    METRIC_PROFIT_GROWTH,
    METRIC_STOCK_PRICE_CAGR,
    METRIC_ROE,
)


# ===========================================================================
# parse_analysis_text() — unit tests
# ===========================================================================


class TestParseAnalysisText:
    """Tests for the pure scalar parser — zero I/O, zero DB calls."""

    def test_standard_format(self):
        """'10 Years: 21%' — canonical format from HDFCBANK."""
        result = parse_analysis_text("10 Years: 21%")
        assert result == [(10, 21.0)]

    def test_colon_with_extra_spaces(self):
        """'5 Years:       24%' — colon present but heavy spacing (SBILIFE)."""
        result = parse_analysis_text("5 Years:       24%")
        assert result == [(5, 24.0)]

    def test_trailing_whitespace(self):
        """'10 Years:     11%             ' — trailing whitespace (TCS sample)."""
        result = parse_analysis_text("10 Years:     11%             ")
        assert result == [(10, 11.0)]

    def test_leading_whitespace(self):
        """'     5 Years:       8%' — leading whitespace (stock_price_cagr observed)."""
        result = parse_analysis_text("     5 Years:       8%")
        assert result == [(5, 8.0)]

    def test_missing_colon(self):
        """'5 Years          14%' — no colon at all (roe field observed in sample)."""
        result = parse_analysis_text("5 Years          14%")
        assert result == [(5, 14.0)]

    def test_decimal_value(self):
        """'10 Years: 21.5%' — decimal value in percentage."""
        result = parse_analysis_text("10 Years: 21.5%")
        assert result == [(10, 21.5)]

    def test_none_input(self):
        """None input must return empty list, not raise."""
        result = parse_analysis_text(None)
        assert result == []

    def test_nan_input(self):
        """float('nan') input must return empty list, not raise."""
        result = parse_analysis_text(float("nan"))
        assert result == []

    def test_empty_string(self):
        """Empty string must return empty list."""
        result = parse_analysis_text("")
        assert result == []

    def test_no_match_plain_text(self):
        """Text with no numeric pattern must return empty list."""
        result = parse_analysis_text("N/A")
        assert result == []

    def test_multiple_pairs_in_one_cell(self):
        """Hypothetical multi-window cell: '10 Years: 21% 5 Years: 15%'."""
        result = parse_analysis_text("10 Years: 21% 5 Years: 15%")
        assert len(result) == 2
        assert (10, 21.0) in result
        assert (5, 15.0) in result

    def test_period_captured_as_int(self):
        """period_years must be int, not string."""
        result = parse_analysis_text("3 Years: 9%")
        assert result == [(3, 9.0)]
        period_years, _ = result[0]
        assert isinstance(period_years, int)

    def test_value_captured_as_float(self):
        """value_pct must be float."""
        result = parse_analysis_text("10 Years: 17%")
        _, value_pct = result[0]
        assert isinstance(value_pct, float)

    def test_10yr_sales_infy(self):
        """INFY compounded_sales_growth: '10 Years:     12%'."""
        result = parse_analysis_text("10 Years:     12%")
        assert result == [(10, 12.0)]

    def test_10yr_roe_tcs(self):
        """TCS roe field: '10 Years:       40%'."""
        result = parse_analysis_text("10 Years:       40%")
        assert result == [(10, 40.0)]

    def test_10yr_stock_price_cagr_leading_spaces(self):
        """'    10 Years:     15%' — leading spaces + colon (INFY stock_price_cagr)."""
        result = parse_analysis_text("    10 Years:     15%")
        assert result == [(10, 15.0)]


# ===========================================================================
# parse_analysis_table() — integration tests
# ===========================================================================


def _make_analysis_df(rows: list[dict]) -> pd.DataFrame:
    """Helper: build a minimal analysis DataFrame."""
    return pd.DataFrame(rows)


def _make_companies_df(company_ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"id": company_ids})


class TestParseAnalysisTable:
    """Integration tests for the bulk table parser."""

    def test_single_company_all_fields(self):
        """Company with clean data in all 4 fields should produce 4 parsed records."""
        analysis_df = _make_analysis_df(
            [
                {
                    "company_id": "TCS",
                    "compounded_sales_growth": "10 Years:     11%",
                    "compounded_profit_growth": "10 Years:          9%",
                    "stock_price_cagr": "10 Years:      14%",
                    "roe": "10 Years:       40%",
                }
            ]
        )
        companies_df = _make_companies_df(["TCS"])
        parsed_df, failures_df = parse_analysis_table(analysis_df, companies_df)

        assert len(parsed_df) == 4
        assert failures_df.empty

    def test_company_with_no_analysis_row(self):
        """Company missing from analysis table → 4 NULL_INPUT failure records."""
        analysis_df = _make_analysis_df([])
        companies_df = _make_companies_df(["RELIANCE"])
        parsed_df, failures_df = parse_analysis_table(analysis_df, companies_df)

        assert parsed_df.empty
        assert len(failures_df) == 4
        assert (failures_df["reason"] == "NULL_INPUT").all()
        assert (failures_df["company_id"] == "RELIANCE").all()

    def test_company_with_none_field(self):
        """A single None field → 1 NULL_INPUT failure, other 3 parse normally."""
        analysis_df = _make_analysis_df(
            [
                {
                    "company_id": "HDFC",
                    "compounded_sales_growth": None,
                    "compounded_profit_growth": "10 Years: 22%",
                    "stock_price_cagr": "10 Years:     15%",
                    "roe": "10 Years:     17%",
                }
            ]
        )
        companies_df = _make_companies_df(["HDFC"])
        parsed_df, failures_df = parse_analysis_table(analysis_df, companies_df)

        assert len(parsed_df) == 3
        assert len(failures_df) == 1
        assert failures_df.iloc[0]["reason"] == "NULL_INPUT"
        assert failures_df.iloc[0]["metric_type"] == METRIC_SALES_GROWTH

    def test_no_match_field_logged_to_failures(self):
        """A field with unrecognisable text → NO_MATCH failure record."""
        analysis_df = _make_analysis_df(
            [
                {
                    "company_id": "XYZ",
                    "compounded_sales_growth": "Not Available",
                    "compounded_profit_growth": "10 Years: 9%",
                    "stock_price_cagr": "10 Years: 14%",
                    "roe": "10 Years: 27%",
                }
            ]
        )
        companies_df = _make_companies_df(["XYZ"])
        parsed_df, failures_df = parse_analysis_table(analysis_df, companies_df)

        assert len(failures_df) == 1
        assert failures_df.iloc[0]["reason"] == "NO_MATCH"
        assert failures_df.iloc[0]["raw_text"] == "Not Available"

    def test_metric_type_assigned_correctly(self):
        """Verify correct metric_type is assigned to each field."""
        analysis_df = _make_analysis_df(
            [
                {
                    "company_id": "INFY",
                    "compounded_sales_growth": "10 Years: 12%",
                    "compounded_profit_growth": "10 Years: 9%",
                    "stock_price_cagr": "10 Years: 15%",
                    "roe": "10 Years: 27%",
                }
            ]
        )
        companies_df = _make_companies_df(["INFY"])
        parsed_df, _ = parse_analysis_table(analysis_df, companies_df)

        metric_types = set(parsed_df["metric_type"].tolist())
        assert METRIC_SALES_GROWTH in metric_types
        assert METRIC_PROFIT_GROWTH in metric_types
        assert METRIC_STOCK_PRICE_CAGR in metric_types
        assert METRIC_ROE in metric_types

    def test_divergence_columns_null_before_cross_validation(self):
        """divergence_pct and flagged_for_review must be None before cross_validate_cagr()."""
        analysis_df = _make_analysis_df(
            [
                {
                    "company_id": "TCS",
                    "compounded_sales_growth": "10 Years: 11%",
                    "compounded_profit_growth": "10 Years: 9%",
                    "stock_price_cagr": "10 Years: 14%",
                    "roe": "10 Years: 40%",
                }
            ]
        )
        companies_df = _make_companies_df(["TCS"])
        parsed_df, _ = parse_analysis_table(analysis_df, companies_df)

        assert parsed_df["divergence_pct"].isna().all()
        assert parsed_df["flagged_for_review"].isna().all()

    def test_multiple_companies(self):
        """All 4 sampled DB companies should parse without failures."""
        rows = [
            {
                "company_id": "HDFCBANK",
                "compounded_sales_growth": "10 Years: 21%",
                "compounded_profit_growth": "10 Years: 22%",
                "stock_price_cagr": "10 Years:     15%",
                "roe": "10 Years:     17%",
            },
            {
                "company_id": "SBILIFE",
                "compounded_sales_growth": "5 Years:       24%",
                "compounded_profit_growth": "5 Years:            6%",
                "stock_price_cagr": "     5 Years:       8%",
                "roe": "5 Years          14%",
            },
            {
                "company_id": "TCS",
                "compounded_sales_growth": "10 Years:     11%             ",
                "compounded_profit_growth": "10 Years:          9%",
                "stock_price_cagr": "    10 Years:      14%",
                "roe": "10 Years:       40%",
            },
            {
                "company_id": "INFY",
                "compounded_sales_growth": "10 Years:     12%",
                "compounded_profit_growth": "10 Years:         9%",
                "stock_price_cagr": "     10 Years:     15%",
                "roe": "10 Years:      27%",
            },
        ]
        analysis_df = _make_analysis_df(rows)
        companies_df = _make_companies_df(["HDFCBANK", "SBILIFE", "TCS", "INFY"])
        parsed_df, failures_df = parse_analysis_table(analysis_df, companies_df)

        assert len(parsed_df) == 16  # 4 companies × 4 fields
        assert failures_df.empty


# ===========================================================================
# cross_validate_cagr() — unit tests
# ===========================================================================


def _make_parsed_row(
    company_id: str,
    metric_type: str,
    period_years: int,
    value_pct: float,
) -> dict:
    return {
        "company_id": company_id,
        "metric_type": metric_type,
        "period_years": period_years,
        "value_pct": value_pct,
        "divergence_pct": None,
        "flagged_for_review": None,
    }


class TestCrossValidateCagr:
    """Tests for CAGR divergence computation and flagging."""

    def _make_cagr_full(self, data: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(data)

    def test_no_divergence_below_threshold(self):
        """Parsed value within 5% of engine → not flagged."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("TCS", METRIC_SALES_GROWTH, 10, 11.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "TCS", "sales_10yr_cagr": 11.5}]  # diff = 0.5%
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert abs(row["divergence_pct"] - (-0.5)) < 0.01
        assert row["flagged_for_review"] == False

    def test_divergence_above_threshold_flagged(self):
        """Parsed value > 5% away from engine → flagged_for_review = True."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("INFY", METRIC_PROFIT_GROWTH, 10, 20.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "INFY", "net_profit_10yr_cagr": 9.0}]  # diff = 11%
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["flagged_for_review"] == True
        assert abs(row["divergence_pct"] - 11.0) < 0.01

    def test_stock_price_cagr_stays_null(self):
        """stock_price_cagr rows must have divergence_pct = None (no engine counterpart)."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("TCS", METRIC_STOCK_PRICE_CAGR, 10, 14.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "TCS", "sales_10yr_cagr": 11.0}]
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["divergence_pct"] is None
        assert row["flagged_for_review"] is None

    def test_roe_stays_null(self):
        """roe rows must have divergence_pct = None."""
        parsed_df = pd.DataFrame([_make_parsed_row("TCS", METRIC_ROE, 10, 40.0)])
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "TCS", "sales_10yr_cagr": 11.0}]
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["divergence_pct"] is None
        assert row["flagged_for_review"] is None

    def test_engine_nan_gives_no_divergence(self):
        """Engine value NaN (INSUFFICIENT flag) → divergence_pct = None, flagged = False."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("ADANIENSOL", METRIC_SALES_GROWTH, 10, 18.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "ADANIENSOL", "sales_10yr_cagr": float("nan")}]
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["divergence_pct"] is None
        assert row["flagged_for_review"] == False

    def test_engine_zero_gives_no_divergence(self):
        """Engine value ≈ 0 → divergence_pct = None (avoid division by zero)."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("XYZ", METRIC_PROFIT_GROWTH, 5, 10.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "XYZ", "net_profit_5yr_cagr": 0.0}]
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["divergence_pct"] is None

    def test_company_not_in_cagr_full(self):
        """Company not in cagr_full.csv → divergence_pct = None."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("UNKNOWN", METRIC_SALES_GROWTH, 10, 12.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "OTHER", "sales_10yr_cagr": 10.0}]
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["divergence_pct"] is None

    def test_5yr_window_lookup(self):
        """Period 5 for sales_growth should look up sales_5yr_cagr."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("SBILIFE", METRIC_SALES_GROWTH, 5, 24.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "SBILIFE", "sales_5yr_cagr": 23.0}]  # diff = 1%
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["flagged_for_review"] == False
        assert abs(row["divergence_pct"] - 1.0) < 0.01

    def test_3yr_window_lookup(self):
        """Period 3 for profit_growth should look up net_profit_3yr_cagr."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("TCS", METRIC_PROFIT_GROWTH, 3, 8.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "TCS", "net_profit_3yr_cagr": 15.0}]  # diff = 7% → flagged
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["flagged_for_review"] == True

    def test_empty_parsed_df_returns_empty(self):
        """Empty parsed_df → returns empty DataFrame without error."""
        empty_df = pd.DataFrame(
            columns=[
                "company_id",
                "metric_type",
                "period_years",
                "value_pct",
                "divergence_pct",
                "flagged_for_review",
            ]
        )
        cagr_full_df = self._make_cagr_full([])
        result = cross_validate_cagr(empty_df, cagr_full_df)
        assert result.empty

    def test_exact_threshold_boundary_not_flagged(self):
        """Divergence exactly at tolerance (5.0%) must NOT be flagged (> not >=)."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("TCS", METRIC_SALES_GROWTH, 10, 16.0)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "TCS", "sales_10yr_cagr": 11.0}]  # diff = exactly 5.0
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["flagged_for_review"] == False

    def test_just_above_threshold_flagged(self):
        """Divergence 5.01% → flagged."""
        parsed_df = pd.DataFrame(
            [_make_parsed_row("TCS", METRIC_SALES_GROWTH, 10, 16.01)]
        )
        cagr_full_df = self._make_cagr_full(
            [{"company_id": "TCS", "sales_10yr_cagr": 11.0}]  # diff = 5.01%
        )
        result = cross_validate_cagr(parsed_df, cagr_full_df, tolerance_pct=5.0)

        row = result.iloc[0]
        assert row["flagged_for_review"] == True
