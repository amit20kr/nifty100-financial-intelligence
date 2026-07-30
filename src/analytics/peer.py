"""
src/analytics/peer.py
=====================
Peer Percentile Ranking Engine.

Sprint 3 - Day 18
Computes percentile ranks for 10 key metrics within each of the 11 peer groups.
- Source of truth: `peer_groups` SQLite table.
- Anchor Year Logic: Reuses the exact AnchorYear CTE from engine.py.
- Debt-Free ICR Bypass: Companies with `icr_at_risk_flag IS NULL` get 1.0 (100th percentile) for ICR.
- D/E Inversion: Uses `rank(pct=True, ascending=False)` so lowest D/E gets 1.0.
- Safe UPSERT: Deletes existing records for the anchor year/metric, then INSERTs.
- Small Group Warning: Logs and persists warnings for peer groups with n < 5.
- Year Mismatch Flag: Flags companies whose anchor year deviates from the peer group's modal year.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Metrics to rank (spec-exact)
METRICS = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "debt_to_equity",
    "free_cash_flow_cr",
    "pat_cagr_5yr",
    "revenue_cagr_5yr",
    "eps_cagr_5yr",
    "interest_coverage",
    "asset_turnover",
]


def _compute_modal_year_mismatch(df: pd.DataFrame) -> pd.DataFrame:
    """Computes the modal year per peer group and sets year_mismatch_flag."""
    # Find mode year per peer group
    modes = (
        df.groupby("peer_group_name")["year"]
        .apply(lambda x: x.mode().iloc[0] if not x.empty else None)
        .reset_index()
    )
    modes.rename(columns={"year": "modal_year"}, inplace=True)

    df = df.merge(modes, on="peer_group_name", how="left")
    df["year_mismatch_flag"] = (df["year"] != df["modal_year"]).astype(int)
    return df


def compute_peer_percentiles(
    db_path: str | Path, output_dir: str | Path = Path("output")
) -> None:
    """Computes peer percentiles and UPSERTs to SQLite."""
    db_path = Path(db_path)
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    # 1. Fetch Data
    query = """
    WITH AnchorYear AS (
        SELECT 
            company_id, 
            year,
            ROW_NUMBER() OVER (
                PARTITION BY company_id 
                ORDER BY 
                    CASE WHEN year LIKE '%-03' THEN 1 ELSE 2 END ASC, 
                    year DESC
            ) as rn
        FROM financial_ratios
    )
    SELECT 
        fr.company_id,
        pg.peer_group_name,
        fr.year,
        fr.icr_at_risk_flag,
        fr.return_on_equity_pct,
        fr.return_on_capital_employed_pct,
        fr.net_profit_margin_pct,
        fr.debt_to_equity,
        fr.free_cash_flow_cr,
        fr.pat_cagr_5yr,
        fr.revenue_cagr_5yr,
        fr.eps_cagr_5yr,
        fr.interest_coverage,
        fr.asset_turnover
    FROM AnchorYear a
    JOIN financial_ratios fr ON a.company_id = fr.company_id AND a.year = fr.year
    LEFT JOIN peer_groups pg ON fr.company_id = pg.company_id
    WHERE a.rn = 1;
    """

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(query, conn)

    # Check unassigned companies
    unassigned = df[df["peer_group_name"].isna()]
    if not unassigned.empty:
        logger.info(
            f"No peer group assigned for {len(unassigned)} companies (e.g. {unassigned['company_id'].iloc[0]}). Skipping them."
        )

    # Filter to only companies with a peer group
    df = df[df["peer_group_name"].notna()].copy()

    # 2. Compute Modal Year Mismatch
    df = _compute_modal_year_mismatch(df)

    # 3. Check Peer Group Sizes and Persist Warnings
    group_sizes = df.groupby("peer_group_name").size()
    small_groups = group_sizes[group_sizes < 5]
    if not small_groups.empty:
        logger.warning(
            f"Small peer groups (n < 5) flagged for unreliable percentiles: {list(small_groups.index)}"
        )
        warnings_df = small_groups.reset_index()
        warnings_df.columns = ["peer_group_name", "company_count"]
        warnings_df["warning"] = "n < 5: percentile ranks may be unreliable"
        warnings_file = output_dir / "peer_group_warnings.csv"
        warnings_df.to_csv(warnings_file, index=False)
        logger.info(f"Persisted small peer group warnings to {warnings_file}")

    # 4. Compute Percentiles per metric per peer group
    records = []

    for group_name, group_df in df.groupby("peer_group_name"):
        for metric in METRICS:
            # Drop purely missing data rows (but retain debt-free ICR explicitly later)
            valid_rows = group_df[
                ["company_id", "year", "year_mismatch_flag", "icr_at_risk_flag", metric]
            ].copy()

            # Identify Debt-Free Companies for ICR
            debt_free_mask = pd.Series(False, index=valid_rows.index)
            if metric == "interest_coverage":
                debt_free_mask = valid_rows["icr_at_risk_flag"].isna()
                # For debt-free companies, we fill their ICR value with a massive sentinel value pre-rank
                # or we just assign them 1.0 explicitly. Let's assign 1.0 explicitly after ranking.
                # But to prevent them from dropping out of the rank denominator, we can fill NA with +inf.
                valid_rows.loc[debt_free_mask, metric] = float("inf")

            # Drop NA (now debt-free have inf, so they won't drop)
            valid_rows = valid_rows.dropna(subset=[metric])

            if valid_rows.empty:
                continue

            # Percentile logic
            if metric == "debt_to_equity":
                # Lower is better -> ascending=False
                ranks = valid_rows[metric].rank(pct=True, ascending=False)
            else:
                # Higher is better
                ranks = valid_rows[metric].rank(pct=True, ascending=True)

            valid_rows["percentile_rank"] = ranks

            # Explicit override for Debt-Free ICR just in case (though +inf already ensures they get 1.0)
            if metric == "interest_coverage":
                valid_rows.loc[
                    valid_rows["icr_at_risk_flag"].isna(), "percentile_rank"
                ] = 1.0

            for _, row in valid_rows.iterrows():
                # Revert +inf back to None for the DB value storage
                val = (
                    None
                    if (
                        metric == "interest_coverage"
                        and pd.isna(row["icr_at_risk_flag"])
                    )
                    else row[metric]
                )

                records.append(
                    {
                        "company_id": row["company_id"],
                        "peer_group_name": group_name,
                        "metric": metric,
                        "value": val,
                        "percentile_rank": row["percentile_rank"],
                        "year": row["year"],
                        "year_mismatch_flag": row["year_mismatch_flag"],
                    }
                )

    result_df = pd.DataFrame(records)

    if result_df.empty:
        logger.warning("No valid metric records found to UPSERT.")
        return

    # 5. Safe UPSERT to Database
    logger.info(
        f"Executing parameterized UPSERT for {len(result_df)} percentile records."
    )

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Prepare distinct composite keys to delete
        keys_to_delete = list(
            result_df[["company_id", "peer_group_name", "metric", "year"]].itertuples(
                index=False, name=None
            )
        )

        # Delete existing overlapping records
        cursor.executemany(
            "DELETE FROM peer_percentiles WHERE company_id = ? AND peer_group_name = ? AND metric = ? AND year = ?",
            keys_to_delete,
        )

        # Insert new records
        insert_query = """
            INSERT INTO peer_percentiles (company_id, peer_group_name, metric, value, percentile_rank, year, year_mismatch_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        insert_data = list(
            result_df[
                [
                    "company_id",
                    "peer_group_name",
                    "metric",
                    "value",
                    "percentile_rank",
                    "year",
                    "year_mismatch_flag",
                ]
            ].itertuples(index=False, name=None)
        )

        cursor.executemany(insert_query, insert_data)
        conn.commit()

    logger.info("Successfully populated peer_percentiles table.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
    )
    compute_peer_percentiles(Path("db/nifty100.db"))
