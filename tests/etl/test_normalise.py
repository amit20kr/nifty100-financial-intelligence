"""
test_normalise.py
=================
Unit tests for src/etl/normaliser.py

Covers normalize_year (20 cases) and normalize_ticker (15 cases) for a
total of 35+ parametrised test scenarios.  All edge cases documented in the
Project Execution Plan §5.1–5.4 are exercised.

Run with:  pytest tests/etl/test_normalise.py -v

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 2
"""

import pytest
import pandas as pd

from src.etl.normaliser import (
    normalize_year,
    normalize_ticker,
    normalize_year_series,
    normalize_ticker_series,
    SENTINEL_PARSE_ERROR,
    SENTINEL_MISSING,
    SENTINEL_TTM,
)


# ===========================================================================
# normalize_year — 20 parametrised cases
# ===========================================================================
class TestNormalizeYear:
    """All year-label normalisation scenarios."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # ── Standard 3-char month abbreviation + 2-digit year ──────────
            ("Mar-23", "2023-03"),  # 1. Typical FY close — hyphen separator
            ("Mar 23", "2023-03"),  # 2. Typical FY close — space separator
            ("Dec-22", "2022-12"),  # 3. Non-March year-end (December)
            ("Jun-23", "2023-06"),  # 4. Non-March year-end (June)
            ("Sep-21", "2021-09"),  # 5. September year-end
            # ── Full 4-digit year ────────────────────────────────────────────
            ("Mar-2023", "2023-03"),  # 6. Hyphen + 4-digit
            ("Mar 2023", "2023-03"),  # 7. Space + 4-digit
            ("Dec-2022", "2022-12"),  # 8. December 4-digit
            # ── Full month name ───────────────────────────────────────────────
            ("March-2023", "2023-03"),  # 9. Full month name hyphen
            ("March 2023", "2023-03"),  # 10. Full month name space
            ("December-2022", "2022-12"),  # 11. Full December name
            # ── FY-style labels ───────────────────────────────────────────────
            ("FY23", "2023-03"),  # 12. FY two-digit
            ("FY2023", "2023-03"),  # 13. FY four-digit
            ("fy23", "2023-03"),  # 14. Lowercase fy
            ("FY 23", "2023-03"),  # 15. FY with space
            # ── Already canonical ─────────────────────────────────────────────
            ("2023-03", "2023-03"),  # 16. Already in target format
            ("2022-12", "2022-12"),  # 17. December canonical
            # ── Bare 4-digit year → defaults to March close ───────────────────
            ("2023", "2023-03"),  # 18. Bare year
            # ── Error cases ───────────────────────────────────────────────────
            ("xyz", SENTINEL_PARSE_ERROR),  # 19. Garbage string
            (None, SENTINEL_PARSE_ERROR),  # 20. Null value
        ],
    )
    def test_normalize_year_parametrized(self, raw: object, expected: str) -> None:
        """normalize_year produces expected canonical output."""
        assert normalize_year(raw) == expected

    def test_nan_returns_parse_error(self) -> None:
        """float NaN (as would come from pd.read_excel on empty cells) → PARSE_ERROR."""
        assert normalize_year(float("nan")) == SENTINEL_PARSE_ERROR

    def test_empty_string_returns_parse_error(self) -> None:
        """Empty string input returns PARSE_ERROR."""
        assert normalize_year("") == SENTINEL_PARSE_ERROR

    def test_whitespace_only_returns_parse_error(self) -> None:
        """Whitespace-only string returns PARSE_ERROR."""
        assert normalize_year("   ") == SENTINEL_PARSE_ERROR

    def test_series_vectorised(self) -> None:
        """normalize_year_series applies correctly across a pandas Series."""
        s = pd.Series(["Mar-23", "Dec-22", "garbage", None])
        result = normalize_year_series(s).tolist()
        assert result == [
            "2023-03",
            "2022-12",
            SENTINEL_PARSE_ERROR,
            SENTINEL_PARSE_ERROR,
        ]

    def test_idempotent(self) -> None:
        """Calling normalize_year on already-canonical output is idempotent."""
        canonical = normalize_year("Mar-23")
        assert normalize_year(canonical) == canonical


# ===========================================================================
# normalize_ticker — 15 parametrised cases
# ===========================================================================
class TestNormalizeTicker:
    """All ticker/company_id normalisation scenarios."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            # ── Normal tickers ─────────────────────────────────────────────
            ("TCS", "TCS"),  # 1. Already correct
            ("tcs", "TCS"),  # 2. Lowercase → uppercase
            ("Tcs", "TCS"),  # 3. Mixed case
            # ── Whitespace handling ────────────────────────────────────────
            (" TCS ", "TCS"),  # 4. Leading/trailing spaces
            ("  INFY  ", "INFY"),  # 5. Multiple spaces both sides
            # ── Special character tickers (must be preserved) ─────────────
            ("M&M", "M&M"),  # 6. Ampersand — Mahindra
            ("BAJAJ-AUTO", "BAJAJ-AUTO"),  # 7. Hyphen — Bajaj Auto
            ("m&m", "M&M"),  # 8. Lowercase with ampersand
            # ── Unusual real-world patterns ───────────────────────────────
            ("HDFCBANK", "HDFCBANK"),  # 9. Long ticker, no separator
            ("ICICIBANK", "ICICIBANK"),  # 10. Another long ticker
            # ── Null / missing ─────────────────────────────────────────────
            (None, SENTINEL_MISSING),  # 11. Python None
            (float("nan"), SENTINEL_MISSING),  # 12. float NaN from Excel
            ("", SENTINEL_MISSING),  # 13. Empty string
            ("   ", SENTINEL_MISSING),  # 14. Whitespace only
            # ── Numeric-ish ticker (edge case) ────────────────────────────
            ("123", "123"),  # 15. Numeric string preserved
        ],
    )
    def test_normalize_ticker_parametrized(self, raw: object, expected: str) -> None:
        """normalize_ticker produces expected canonical output."""
        assert normalize_ticker(raw) == expected

    def test_series_vectorised(self) -> None:
        """normalize_ticker_series applies correctly across a pandas Series."""
        s = pd.Series(["tcs", " INFY ", None, "M&M"])
        result = normalize_ticker_series(s).tolist()
        assert result == ["TCS", "INFY", SENTINEL_MISSING, "M&M"]

    def test_idempotent(self) -> None:
        """Calling normalize_ticker on already-normalised output is idempotent."""
        canonical = normalize_ticker("  tcs  ")
        assert normalize_ticker(canonical) == canonical

    def test_pandas_na_returns_missing(self) -> None:
        """pd.NA value (NAType) is treated as missing — not float, requires pd.isna() guard."""
        # pd.NA is a pandas NAType, distinct from float('nan') and None
        result = normalize_ticker(pd.NA)
        assert (
            result == SENTINEL_MISSING
        ), f"Expected '{SENTINEL_MISSING}' for pd.NA input, got '{result}'"


# ===========================================================================
# Loader smoke test — verifies the DataLoader reads real files without error
# ===========================================================================
class TestDataLoaderSmoke:
    """Smoke tests that require actual data files on disk."""

    def test_profitandloss_loads_successfully(self, raw_data_dir) -> None:
        """profitandloss.xlsx should load ≥ 1000 rows with correct columns."""
        from src.etl.loader import DataLoader

        loader = DataLoader()
        frames = loader.load_all()
        df = frames.get("profitandloss")

        assert df is not None, "profitandloss DataFrame should not be None"
        assert len(df) >= 1000, f"Expected ≥1000 rows, got {len(df)}"
        expected_cols = {"company_id", "year", "sales", "net_profit", "eps"}
        assert expected_cols.issubset(
            df.columns
        ), f"Missing columns: {expected_cols - set(df.columns)}"

    def test_companies_loads_92_rows(self, raw_data_dir) -> None:
        """companies.xlsx should load exactly 92 companies."""
        from src.etl.loader import DataLoader

        loader = DataLoader()
        frames = loader.load_all()
        df = frames.get("companies")

        assert df is not None
        assert len(df) == 92, f"Expected 92 companies, got {len(df)}"

    def test_no_missing_tickers_in_companies(self, raw_data_dir) -> None:
        """No company_id or id should be MISSING after normalisation."""
        from src.etl.loader import DataLoader

        loader = DataLoader()
        frames = loader.load_all()
        companies = frames.get("companies")

        assert companies is not None
        # companies uses 'id' as the ticker column
        ticker_col = "id" if "id" in companies.columns else "company_id"
        bad = companies[ticker_col].isin([SENTINEL_MISSING, SENTINEL_PARSE_ERROR])
        assert (
            not bad.any()
        ), f"Found {bad.sum()} MISSING/PARSE_ERROR tickers in companies table"

    def test_no_parse_errors_in_profitandloss_years(self, raw_data_dir) -> None:
        """No year values should be PARSE_ERROR after normalisation.

        NOTE: TTM (Trailing Twelve Months) rows exist in the real data and are
        preserved as SENTINEL_TTM — not treated as PARSE_ERROR. Only truly
        unparseable values (e.g. '2024.5') are flagged as PARSE_ERROR.
        """
        from src.etl.loader import DataLoader

        loader = DataLoader()
        frames = loader.load_all()
        df = frames.get("profitandloss")

        assert df is not None
        # Exclude TTM rows — these are valid sentinel values, not errors
        non_ttm = df[df["year"] != SENTINEL_TTM]
        bad = (non_ttm["year"] == SENTINEL_PARSE_ERROR).sum()
        assert bad == 0, (
            f"{bad} unexpected PARSE_ERROR year values found in profitandloss "
            f"(TTM rows are excluded from this check)"
        )

    def test_year_format_is_canonical(self, raw_data_dir) -> None:
        """All normalised years must be 'YYYY-MM', 'TTM', or 'PARTIAL_YEAR'.

        TTM (Trailing Twelve Months) and PARTIAL_YEAR are valid special-purpose
        sentinels and are explicitly allowed here.
        """
        import re
        from src.etl.loader import DataLoader
        from src.etl.normaliser import SENTINEL_TTM, SENTINEL_PARTIAL

        loader = DataLoader()
        frames = loader.load_all()
        df = frames.get("profitandloss")

        assert df is not None
        pattern = re.compile(r"^\d{4}-\d{2}$")
        allowed_sentinels = {SENTINEL_TTM, SENTINEL_PARTIAL}

        def is_valid(v: str) -> bool:
            return bool(pattern.match(str(v))) or v in allowed_sentinels

        invalid = df["year"].apply(lambda v: not is_valid(str(v)))
        assert (
            not invalid.any()
        ), f"Non-canonical year values found: {df.loc[invalid, 'year'].unique()}"

    def test_audit_log_generated(self, tmp_path, monkeypatch) -> None:
        """load_all() must produce a load_audit.csv in the output directory."""
        from src.etl import loader as loader_module

        monkeypatch.setattr(loader_module, "OUTPUT_DIR", tmp_path)
        ldr = loader_module.DataLoader()
        ldr.load_all()
        ldr._write_audit_log()

        audit_file = tmp_path / "load_audit.csv"
        assert audit_file.exists(), "load_audit.csv was not generated"

        import pandas as pd

        audit_df = pd.read_csv(audit_file)
        assert (
            len(audit_df) == 12
        ), f"Expected 12 audit rows (one per dataset), got {len(audit_df)}"
        assert "rows_in" in audit_df.columns
        assert "rows_out" in audit_df.columns
        assert "status" in audit_df.columns
