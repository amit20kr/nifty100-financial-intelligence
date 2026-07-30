import pytest
import os
import sqlite3
from src.screener.engine import FilterEngine


@pytest.fixture
def test_db_and_config(tmp_path):
    db_path = tmp_path / "test.db"
    config_path = tmp_path / "config.yaml"

    # 1. Create a minimal schema and data to test engine
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE financial_ratios (
            company_id TEXT, year TEXT, debt_to_equity REAL, interest_coverage REAL,
            icr_at_risk_flag INTEGER, pat_cagr_5yr REAL,
            return_on_equity_pct REAL, return_on_capital_employed_pct REAL,
            net_profit_margin_pct REAL, free_cash_flow_cr REAL,
            cash_from_operations_cr REAL, revenue_cagr_5yr REAL
        )"""
        )
        conn.execute(
            "CREATE TABLE profitandloss (company_id TEXT, year TEXT, sales REAL, net_profit REAL)"
        )
        conn.execute(
            "CREATE TABLE market_cap (company_id TEXT, year TEXT, market_cap_crore REAL, pe_ratio REAL, pb_ratio REAL, dividend_yield_pct REAL, enterprise_value_crore REAL)"
        )
        conn.execute("CREATE TABLE sectors (company_id TEXT, broad_sector TEXT)")

        # Company A: normal company, latest year 2024-03
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('A', '2024-03', 1.5, 3.0, 0, 10.0, 15.0, 18.0, 12.0, 500.0, 600.0, 10.0)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('A', '2024-03', 1000, 100)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('A', '2024-03', 5000, 10, 2, 1.0, 5500)"
        )
        conn.execute("INSERT INTO sectors VALUES ('A', 'Technology')")

        # Company B: Financials company (should bypass D/E filter)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('B', '2024-03', 5.0, 2.0, 0, 5.0, 12.0, 14.0, 10.0, 300.0, 400.0, 8.0)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('B', '2024-03', 2000, 200)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('B', '2024-03', 10000, 15, 3, 2.0, 11000)"
        )
        conn.execute("INSERT INTO sectors VALUES ('B', 'Financials')")

        # Company C: Debt-free company (should bypass ICR min)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('C', '2024-03', 0.0, NULL, NULL, NULL, 20.0, 22.0, 15.0, 200.0, 300.0, 12.0)"
        )  # NULL CAGR
        conn.execute("INSERT INTO profitandloss VALUES ('C', '2024-03', 500, 50)")
        conn.execute(
            "INSERT INTO market_cap VALUES ('C', '2024-03', 1000, 20, 4, 0.0, 1000)"
        )
        conn.execute("INSERT INTO sectors VALUES ('C', 'Technology')")

        # Company D: Has missing market_cap row (should fail closed on valuation metrics)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('D', '2024-03', 1.0, 5.0, 0, 15.0, 18.0, 20.0, 14.0, 700.0, 800.0, 11.0)"
        )
        conn.execute("INSERT INTO profitandloss VALUES ('D', '2024-03', 1500, 150)")
        conn.execute("INSERT INTO sectors VALUES ('D', 'Healthcare')")
        # No market_cap row for D in 2024-03

        # Company E: Multi-year anchor test (2024-03 vs 2024-09, should pick 2024-03)
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('E', '2024-03', 2.0, 1.0, 1, 8.0, 10.0, 12.0, 8.0, -100.0, 50.0, 5.0)"
        )
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('E', '2024-09', 1.0, 1.0, 1, 8.0, 10.0, 12.0, 8.0, -50.0, 60.0, 6.0)"
        )

    config_yaml = """
metrics:
  sales:
    column: sales
    operator: min
  debt_to_equity:
    column: debt_to_equity
    operator: max
  interest_coverage:
    column: interest_coverage
    operator: min
  market_cap_crore:
    column: market_cap_crore
    operator: min
  pat_cagr_5yr:
    column: pat_cagr_5yr
    operator: min
    """
    config_path.write_text(config_yaml)

    os.environ["FINANCIALS_SECTOR_LABEL"] = "Financials"
    yield db_path, config_path


def test_engine_population_integrity(test_db_and_config):
    db_path, config_path = test_db_and_config
    engine = FilterEngine(db_path, config_path)

    # Assert len(engine_output) == count of distinct companies with anchor-year financial_ratios row
    # We have 5 distinct companies (A, B, C, D, E) in financial_ratios
    res = engine.apply({})
    assert len(res) == 5, "LEFT JOINs should not drop any rows."

    # Check that E's anchor year is '2024-03' because of the tie break
    e_row = res[res["company_id"] == "E"]
    assert e_row.iloc[0]["year"] == "2024-03", "Anchor year priority logic failed."


def test_engine_de_bypass(test_db_and_config):
    db_path, config_path = test_db_and_config
    engine = FilterEngine(db_path, config_path)

    # Require D/E <= 2.0
    res = engine.apply({"debt_to_equity": 2.0})

    companies = res["company_id"].tolist()
    assert "A" in companies  # D/E = 1.5 <= 2.0
    assert "B" in companies  # D/E = 5.0, but Financials bypass
    assert "E" in companies  # D/E = 2.0


def test_engine_icr_debt_free_bypass(test_db_and_config):
    db_path, config_path = test_db_and_config
    engine = FilterEngine(db_path, config_path)

    # Require ICR >= 2.5
    res = engine.apply({"interest_coverage": 2.5})

    companies = res["company_id"].tolist()
    assert "A" in companies  # 3.0 >= 2.5
    assert "B" not in companies  # 2.0 < 2.5, no bypass for Financials on ICR
    assert "C" in companies  # NULL ICR, but debt-free (icr_at_risk_flag is NULL) bypass


def test_engine_fail_closed_missing_market_cap(test_db_and_config):
    db_path, config_path = test_db_and_config
    engine = FilterEngine(db_path, config_path)

    # Require Market Cap >= 0
    res = engine.apply({"market_cap_crore": 0})

    companies = res["company_id"].tolist()
    assert (
        "D" not in companies
    )  # Missing market_cap row -> Market Cap is None -> fail closed


def test_engine_fail_closed_null_cagr(test_db_and_config):
    db_path, config_path = test_db_and_config
    engine = FilterEngine(db_path, config_path)

    # Require PAT CAGR >= 0
    res = engine.apply({"pat_cagr_5yr": 0})

    companies = res["company_id"].tolist()
    assert "C" not in companies  # NULL CAGR -> fail closed
