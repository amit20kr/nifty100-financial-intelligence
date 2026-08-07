"""
scripts/run_day29_parser.py
---------------------------
Day 29 execution script — NLP Analysis Text Parser.

Generates:
    output/analysis_parsed.csv   — structured CAGR values from analysis table
    output/parse_failures.csv    — non-matching cells, audit trail

Reads:
    db/nifty100.db               — analysis + companies tables
    output/cagr_full.csv         — sole cross-validation source (3yr/5yr/10yr)

Usage (from project root, with .venv activated):
    python scripts/run_day29_parser.py
"""

import logging
import os
import sqlite3
import sys

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nlp.parser import parse_analysis_table, cross_validate_cagr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("day29_parser")


def main() -> None:
    db_path = os.getenv("DB_PATH", "db/nifty100.db")
    output_dir = os.getenv("OUTPUT_DIR", "output")
    os.makedirs(output_dir, exist_ok=True)

    cagr_csv_path = os.path.join(output_dir, "cagr_full.csv")
    parsed_csv_path = os.path.join(output_dir, "analysis_parsed.csv")
    failures_csv_path = os.path.join(output_dir, "parse_failures.csv")

    # -------------------------------------------------------------------------
    # Step 1: Confirm cagr_full.csv exists — mandatory pre-condition
    # -------------------------------------------------------------------------
    if not os.path.exists(cagr_csv_path):
        logger.error(
            "MISSING: %s — run generate_cagr_full.py first before Day 29 cross-validation.",
            cagr_csv_path,
        )
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Step 2: Bulk-load once — zero per-row DB calls in the parser
    # -------------------------------------------------------------------------
    logger.info("Loading analysis and companies tables from %s ...", db_path)
    with sqlite3.connect(db_path) as conn:
        analysis_df = pd.read_sql_query("SELECT * FROM analysis", conn)
        companies_df = pd.read_sql_query("SELECT id, company_name FROM companies", conn)

    logger.info(
        "  analysis rows: %d  |  companies: %d", len(analysis_df), len(companies_df)
    )

    # -------------------------------------------------------------------------
    # Step 3: Parse all analysis text fields in-memory
    # -------------------------------------------------------------------------
    logger.info("Parsing analysis text fields ...")
    parsed_df, failures_df = parse_analysis_table(analysis_df, companies_df)

    # -------------------------------------------------------------------------
    # Step 4: Load cagr_full.csv and cross-validate
    # -------------------------------------------------------------------------
    logger.info("Loading %s for cross-validation ...", cagr_csv_path)
    cagr_full_df = pd.read_csv(cagr_csv_path)

    logger.info("Running CAGR cross-validation ...")
    parsed_df = cross_validate_cagr(parsed_df, cagr_full_df)

    # -------------------------------------------------------------------------
    # Step 5: Write outputs
    # -------------------------------------------------------------------------
    parsed_df.to_csv(parsed_csv_path, index=False)
    failures_df.to_csv(failures_csv_path, index=False)

    logger.info("Written: %s  (%d rows)", parsed_csv_path, len(parsed_df))
    logger.info("Written: %s  (%d rows)", failures_csv_path, len(failures_df))

    # -------------------------------------------------------------------------
    # Step 6: Summary report
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("DAY 29 — NLP ANALYSIS TEXT PARSER — SUMMARY")
    print("=" * 60)

    print(f"\n  Companies in DB         : {len(companies_df)}")
    print(f"  Companies with analysis : {analysis_df['company_id'].nunique()}")
    print(
        f"  Companies missing data  : {len(companies_df) - analysis_df['company_id'].nunique()}"
    )

    print(f"\n  Parsed records          : {len(parsed_df)}")
    print(f"  Failure records         : {len(failures_df)}")

    if not failures_df.empty:
        reason_counts = failures_df["reason"].value_counts()
        for reason, count in reason_counts.items():
            print(f"    +-- {reason}: {count}")

    # Cross-validation summary
    cv_rows = parsed_df[parsed_df["divergence_pct"].notna()]
    flagged_rows = parsed_df[parsed_df["flagged_for_review"] == True]  # noqa: E712
    print(f"\n  Cross-validated rows    : {len(cv_rows)}")
    print(f"  Flagged for review      : {len(flagged_rows)}")

    if not flagged_rows.empty:
        print("\n  ⚠ FLAGGED DIVERGENCES (>5%):")
        for _, r in flagged_rows.iterrows():
            print(
                f"    [{r['company_id']} / {r['metric_type']} / {int(r['period_years'])}yr]"
                f"  parsed={r['value_pct']:.1f}%  divergence={r['divergence_pct']:+.2f}%"
            )

    # Metric breakdown
    if not parsed_df.empty:
        print("\n  Parsed breakdown by metric_type:")
        for mt, grp in parsed_df.groupby("metric_type"):
            print(f"    {mt}: {len(grp)} records")

    print("\n  Spot-check (first 3 sales_growth rows vs cagr_full.csv):")
    sg = parsed_df[parsed_df["metric_type"] == "sales_growth"].head(3)
    if sg.empty:
        print("    (no sales_growth records parsed)")
    else:
        for _, r in sg.iterrows():
            print(
                f"    [{r['company_id']} / {int(r['period_years'])}yr]"
                f"  parsed={r['value_pct']:.1f}%  divergence={r['divergence_pct']}"
            )

    print("\n" + "=" * 60)
    print("[DONE] Day 29 Complete")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
