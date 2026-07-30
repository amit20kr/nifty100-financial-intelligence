"""
tests/analytics/test_peer.py
============================
Day 18 — Automated tests for peer percentile rankings.

Validates:
1. Debt-free companies are forced to 100th percentile (1.0) on Interest Coverage.
2. D/E inversion: lowest D/E gets 100th percentile (1.0).
3. Null metric values correctly generate NaNs (omitted from output/percentile denominator), except ICR.
4. Year mismatch flag identifies non-modal anchor years within a peer group.
5. Small peer group persistence and correct warnings.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.analytics.peer import compute_peer_percentiles


@pytest.fixture
def synthetic_peer_db_and_out(tmp_path):
    """Build a synthetic DataFrame and DB for unit testing peer rankings."""
    db_path = tmp_path / "test.db"
    out_dir = tmp_path / "output"
    os.makedirs(out_dir, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE companies (id TEXT PRIMARY KEY)")
        conn.execute(
            """CREATE TABLE peer_groups (
            id TEXT PRIMARY KEY,
            peer_group_name TEXT,
            company_id TEXT,
            is_benchmark INTEGER
        )"""
        )
        conn.execute(
            """CREATE TABLE financial_ratios (
            company_id TEXT, year TEXT, debt_to_equity REAL, interest_coverage REAL,
            icr_at_risk_flag INTEGER, pat_cagr_5yr REAL, return_on_equity_pct REAL,
            return_on_capital_employed_pct REAL, net_profit_margin_pct REAL,
            free_cash_flow_cr REAL, revenue_cagr_5yr REAL, eps_cagr_5yr REAL,
            asset_turnover REAL
        )"""
        )
        conn.execute(
            """CREATE TABLE peer_percentiles (
            company_id TEXT, peer_group_name TEXT, metric TEXT,
            value REAL, percentile_rank REAL, year TEXT, year_mismatch_flag INTEGER,
            PRIMARY KEY (company_id, peer_group_name, metric, year)
        )"""
        )

        # Group 1: IT Services (Normal sizes to test ranking logic)
        for c in ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM"]:
            conn.execute(f"INSERT INTO companies VALUES ('{c}')")
            conn.execute(
                f"INSERT INTO peer_groups VALUES ('{c}_grp', 'IT Services', '{c}', 0)"
            )

        # Add a debt-free company (TCS), missing ICR
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('TCS', '2024-03', 0.0, NULL, NULL, 10.0, 30.0, 35.0, 20.0, 1000.0, 10.0, 10.0, 1.5)"
        )
        # Add normal companies
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('INFY', '2024-03', 0.1, 15.0, 0, 8.0, 25.0, 30.0, 15.0, 800.0, 8.0, 8.0, 1.2)"
        )
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('HCLTECH', '2024-03', 0.2, 10.0, 0, 6.0, 20.0, 25.0, 12.0, 600.0, 6.0, 6.0, 1.0)"
        )
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('WIPRO', '2024-03', 0.3, 5.0, 1, 4.0, 15.0, 20.0, 10.0, 400.0, 4.0, 4.0, 0.8)"
        )
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('TECHM', '2024-03', 0.4, 2.0, 1, 2.0, 10.0, 15.0, 8.0, 200.0, 2.0, 2.0, 0.6)"
        )

        # LTIM has a different year (2024-09 instead of modal 2024-03) -> Mismatch flag
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('LTIM', '2024-09', 0.5, 1.0, 1, 1.0, 5.0, 10.0, 5.0, 100.0, 1.0, 1.0, 0.5)"
        )

        # Group 2: Small Group (n=3)
        for c in ["A", "B", "C"]:
            conn.execute(f"INSERT INTO companies VALUES ('{c}')")
            conn.execute(
                f"INSERT INTO peer_groups VALUES ('{c}_grp', 'Small Group', '{c}', 0)"
            )
            conn.execute(
                f"INSERT INTO financial_ratios VALUES ('{c}', '2024-03', 1.0, 10.0, 0, 5.0, 10.0, 10.0, 10.0, 100.0, 5.0, 5.0, 1.0)"
            )

        # Group 3: Unassigned Company
        conn.execute("INSERT INTO companies VALUES ('UNASSIGNED')")
        conn.execute(
            "INSERT INTO financial_ratios VALUES ('UNASSIGNED', '2024-03', 1.0, 10.0, 0, 5.0, 10.0, 10.0, 10.0, 100.0, 5.0, 5.0, 1.0)"
        )

    return str(db_path), str(out_dir)


class TestPeerPercentiles:
    def test_debt_free_icr_forced_to_100_percentile(self, synthetic_peer_db_and_out):
        """TCS has ICR=NULL and icr_at_risk_flag=NULL. Must rank 1.0 in IT Services."""
        db_path, out_dir = synthetic_peer_db_and_out
        compute_peer_percentiles(db_path, out_dir)

        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM peer_percentiles WHERE metric='interest_coverage'", conn
            )

        tcs_row = df[
            (df["company_id"] == "TCS") & (df["peer_group_name"] == "IT Services")
        ].iloc[0]
        assert (
            tcs_row["percentile_rank"] == 1.0
        ), "Debt-free company must get 1.0 percentile for ICR"
        assert pd.isna(tcs_row["value"]), "Underlying value must remain NULL in DB"

    def test_de_inversion_lowest_gets_highest_rank(self, synthetic_peer_db_and_out):
        """TCS has lowest D/E (0.0). Must rank 1.0 in IT Services."""
        db_path, out_dir = synthetic_peer_db_and_out
        compute_peer_percentiles(db_path, out_dir)

        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM peer_percentiles WHERE metric='debt_to_equity' AND peer_group_name='IT Services'",
                conn,
            )

        tcs_row = df[df["company_id"] == "TCS"].iloc[0]
        assert tcs_row["percentile_rank"] == 1.0, "Lowest D/E must get 1.0 percentile"

        # LTIM has highest D/E (0.5), must rank lowest (1/6 = 0.166...)
        ltim_row = df[df["company_id"] == "LTIM"].iloc[0]
        assert abs(ltim_row["percentile_rank"] - (1 / 6)) < 1e-4

    def test_year_mismatch_flag_correctly_identified(self, synthetic_peer_db_and_out):
        """LTIM anchor year is 2024-09, while mode is 2024-03. Should have year_mismatch_flag=1."""
        db_path, out_dir = synthetic_peer_db_and_out
        compute_peer_percentiles(db_path, out_dir)

        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query("SELECT * FROM peer_percentiles", conn)

        ltim = df[df["company_id"] == "LTIM"]
        assert (
            ltim["year_mismatch_flag"] == 1
        ).all(), "LTIM must have year_mismatch_flag=1"

        tcs = df[df["company_id"] == "TCS"]
        assert (
            tcs["year_mismatch_flag"] == 0
        ).all(), "TCS must have year_mismatch_flag=0 (modal)"

    def test_small_group_warning_persisted(self, synthetic_peer_db_and_out):
        """Groups with n < 5 must be written to peer_group_warnings.csv."""
        db_path, out_dir = synthetic_peer_db_and_out
        compute_peer_percentiles(db_path, out_dir)

        warnings_file = Path(out_dir) / "peer_group_warnings.csv"
        assert warnings_file.exists(), "peer_group_warnings.csv must be created"

        warnings = pd.read_csv(warnings_file)
        assert "Small Group" in warnings["peer_group_name"].values
        assert "IT Services" not in warnings["peer_group_name"].values

    def test_unassigned_companies_skipped(self, synthetic_peer_db_and_out):
        """Companies without a peer group must not have records in peer_percentiles."""
        db_path, out_dir = synthetic_peer_db_and_out
        compute_peer_percentiles(db_path, out_dir)

        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(
                "SELECT * FROM peer_percentiles WHERE company_id='UNASSIGNED'", conn
            )

        assert df.empty, "Unassigned companies must be skipped completely"

    def test_composite_pk_allows_multigroup(self, synthetic_peer_db_and_out):
        """A single company in multiple peer groups must not cause a PK violation on UPSERT."""
        db_path, out_dir = synthetic_peer_db_and_out

        # Add TCS to a second group
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO peer_groups VALUES ('tcs_grp_2', 'Tech Conglomerates', 'TCS', 0)"
            )

        # If the PK is properly defined as (company_id, peer_group_name, metric, year), this will not raise an IntegrityError
        compute_peer_percentiles(db_path, out_dir)

        with sqlite3.connect(db_path) as conn:
            cnt = conn.execute(
                "SELECT COUNT(DISTINCT peer_group_name) FROM peer_percentiles WHERE company_id='TCS'"
            ).fetchone()[0]

        assert cnt == 2, "TCS should have percentile ranks in 2 different groups"
