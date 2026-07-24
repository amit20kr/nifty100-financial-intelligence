"""
tests/etl/test_financial_ratios_population.py
----------------------------------------------
Integration tests for Day 12 financial_ratios population.

These tests assert exit-criteria conditions automatically under pytest / CI,
eliminating the need for manual one-off `python -c` verification snippets.

Per the Day 12 plan review, three categories of assertions are required:
  1. Row count >= 1,100
  2. Distinct company count == 92
  3. No column is entirely NULL among the 14+ required KPI columns

Run with:
    .venv/Scripts/pytest tests/etl/test_financial_ratios_population.py -v

Pre-condition: scripts/populate_ratios.py must have been executed to populate the table.
These are integration tests against the live DB — they do NOT call populate_ratios.py
internally (that would make test runs destructive and slow). Use the Makefile `populate`
target to run the population script before this suite.
"""

import os
import sqlite3

import pytest

pytestmark = pytest.mark.requires_populated_db
"""
All tests in this file require scripts/populate_ratios.py to have been run first.
The standard test suite (pytest tests/) calls test_load_all_and_idempotency which
resets the DB. Run this suite separately:

    .venv/Scripts/python scripts/populate_ratios.py
    .venv/Scripts/pytest tests/etl/test_financial_ratios_population.py -v

Or via make:
    make populate
    make test-integration
"""

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")

# Minimum thresholds — aligned with Sprint 2 exit criteria
MIN_ROWS = 1100
EXPECTED_COMPANIES = 92

# All 14+ KPI columns required by spec; none may be entirely NULL after Day 12
REQUIRED_NON_NULL_COLS = [
    # Sprint 1 pre-seeded (overwritten by engine)
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "return_on_equity_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "free_cash_flow_cr",
    "capex_cr",
    "earnings_per_share",
    "book_value_per_share",
    "dividend_payout_ratio_pct",
    "total_debt_cr",
    "cash_from_operations_cr",
    # Sprint 2 Day 08–11 computed
    "return_on_capital_employed_pct",
    "return_on_assets_pct",
    "net_debt_cr",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "composite_quality_score",
    "cashflow_pattern_code",
    "capex_intensity_pct",
    "fcf_conversion_pct",
]


@pytest.fixture(scope="module")
def db_conn():
    """Module-scoped DB connection to the populated live database."""
    if not os.path.exists(DB_PATH):
        pytest.skip(f"Database not found at {DB_PATH}. Run 'make load' first.")
    conn = sqlite3.connect(DB_PATH)
    yield conn
    conn.close()


def test_row_count_meets_exit_criterion(db_conn):
    """EXIT CRITERION: SELECT COUNT(*) FROM financial_ratios >= 1100."""
    row_count = db_conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    assert row_count >= MIN_ROWS, (
        f"financial_ratios has {row_count} rows — exit criterion requires >= {MIN_ROWS}. "
        "Run scripts/populate_ratios.py to populate computed KPIs."
    )


def test_distinct_company_count(db_conn):
    """All 92 companies must have at least one row in financial_ratios."""
    company_count = db_conn.execute(
        "SELECT COUNT(DISTINCT company_id) FROM financial_ratios"
    ).fetchone()[0]
    assert company_count == EXPECTED_COMPANIES, (
        f"Only {company_count}/{EXPECTED_COMPANIES} companies present in financial_ratios. "
        "Some companies are missing entirely — check ETL orphan drops."
    )


@pytest.mark.parametrize("col", REQUIRED_NON_NULL_COLS)
def test_column_has_at_least_one_non_null_value(db_conn, col):
    """EXIT CRITERION: no column is null-only. Every required KPI must have >= 1 populated row."""
    try:
        non_null_count = db_conn.execute(
            f"SELECT COUNT(*) FROM financial_ratios WHERE {col} IS NOT NULL"
        ).fetchone()[0]
    except sqlite3.OperationalError as e:
        pytest.fail(f"Column '{col}' does not exist in financial_ratios: {e}")

    assert non_null_count > 0, (
        f"Column '{col}' is entirely NULL — exit criterion 'zero null-only columns' violated. "
        "Run scripts/populate_ratios.py to populate this KPI."
    )


def test_capital_allocation_csv_exists():
    """Day 11/12 deliverable: output/capital_allocation.csv must exist and be non-empty."""
    csv_path = os.path.join(os.getenv("OUTPUT_DIR", "output"), "capital_allocation.csv")
    assert os.path.exists(
        csv_path
    ), "output/capital_allocation.csv not found. Run scripts/populate_ratios.py."
    with open(csv_path, "r") as f:
        lines = f.readlines()
    # Header + at least one data row
    assert len(lines) > 1, "capital_allocation.csv is empty (header only)."


def test_capital_allocation_csv_columns():
    """Verify capital_allocation.csv has the 8 required columns."""
    csv_path = os.path.join(os.getenv("OUTPUT_DIR", "output"), "capital_allocation.csv")
    if not os.path.exists(csv_path):
        pytest.skip("capital_allocation.csv not found — run populate_ratios.py first.")
    with open(csv_path, "r") as f:
        header = f.readline().strip()
    expected_cols = {
        "company_id",
        "year",
        "cfo_sign",
        "cfi_sign",
        "cff_sign",
        "pattern_code",
        "pattern_label",
        "pattern_flag",
    }
    actual_cols = set(header.split(","))
    assert (
        expected_cols == actual_cols
    ), f"capital_allocation.csv missing columns: {expected_cols - actual_cols}"


def test_capital_allocation_csv_row_parity(db_conn):
    """
    CSV row count + rows with NULL pattern code must equal total DB row count.
    This ensures we didn't silently drop any rows during CSV emission.
    """
    csv_path = os.path.join(os.getenv("OUTPUT_DIR", "output"), "capital_allocation.csv")
    if not os.path.exists(csv_path):
        pytest.skip("capital_allocation.csv not found.")

    with open(csv_path, "r") as f:
        # Subtract 1 for the header
        csv_rows = sum(1 for _ in f) - 1

    db_rows = db_conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    null_pattern_rows = db_conn.execute(
        "SELECT COUNT(*) FROM financial_ratios WHERE cashflow_pattern_code IS NULL"
    ).fetchone()[0]

    assert (
        csv_rows + null_pattern_rows == db_rows
    ), f"CSV row parity failed: {csv_rows} (CSV) + {null_pattern_rows} (NULL patterns) != {db_rows} (Total DB rows)"


def test_ratio_edge_cases_log_exists():
    """Day 13 deliverable: ratio_edge_cases.log must exist."""
    log_path = os.path.join(os.getenv("OUTPUT_DIR", "output"), "ratio_edge_cases.log")
    assert os.path.exists(log_path), (
        "output/ratio_edge_cases.log not found. "
        "Run scripts/populate_ratios.py to generate cross-check logs."
    )


def test_financial_ratios_schema_has_all_sprint2_columns(db_conn):
    """Schema completeness: all 20+ Sprint 2 columns must exist in financial_ratios."""
    existing_cols = {
        row[1]
        for row in db_conn.execute("PRAGMA table_info(financial_ratios)").fetchall()
    }
    sprint2_cols = {
        "return_on_capital_employed_pct",
        "return_on_assets_pct",
        "net_debt_cr",
        "icr_label",
        "icr_at_risk_flag",
        "high_leverage_flag",
        "revenue_cagr_5yr",
        "pat_cagr_5yr",
        "eps_cagr_5yr",
        "revenue_cagr_5yr_flag",
        "pat_cagr_5yr_flag",
        "eps_cagr_5yr_flag",
        "composite_quality_score",
        "composite_quality_score_flag",
        "cfo_quality_label",
        "cashflow_pattern_code",
        "cashflow_pattern_label",
        "pattern_flag",
        "capex_intensity_label",
        "capex_intensity_pct",
        "fcf_conversion_flag",
        "fcf_conversion_pct",
    }
    missing = sprint2_cols - existing_cols
    assert not missing, (
        f"Sprint 2 columns missing from financial_ratios schema: {missing}. "
        "Run db/migrations/migrate.py to upgrade an existing DB."
    )


def test_cashflow_pattern_labels_are_spec_compliant(db_conn):
    """All pattern labels in DB must be from the 8 spec-defined set (+ Unclassified for gap)."""
    valid_labels = {
        "Reinvestor",
        "Shareholder Returns",
        "Liquidating Assets",
        "Distress Signal",
        "Growth Funded by Debt",
        "Cash Accumulator",
        "Pre-Revenue",
        "Mixed",
        "Unclassified",
    }
    actual_labels = {
        row[0]
        for row in db_conn.execute(
            "SELECT DISTINCT cashflow_pattern_label FROM financial_ratios "
            "WHERE cashflow_pattern_label IS NOT NULL"
        ).fetchall()
    }
    invalid = actual_labels - valid_labels
    assert not invalid, f"Invalid pattern labels found in DB (not in spec): {invalid}"


def test_upsert_idempotency_row_count(db_conn):
    """
    Row count must be stable — running populate_ratios.py a second time must not
    add duplicate rows (UPSERT ON CONFLICT guarantee). This test checks the invariant
    after populate has already run; the actual two-run comparison is in the Makefile
    idempotency target (make populate && make populate).
    """
    row_count_before = db_conn.execute(
        "SELECT COUNT(*) FROM financial_ratios"
    ).fetchone()[0]
    # Confirm we're in a post-populate state (not empty)
    assert (
        row_count_before >= MIN_ROWS
    ), "Table is not populated — run scripts/populate_ratios.py before this test."
