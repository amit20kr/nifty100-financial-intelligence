import os
import sqlite3
import pandas as pd
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("capital_allocation")


def _extract_year(y_str: str) -> int:
    try:
        return int(str(y_str)[:4])
    except:
        return 0


def run_qa_gate(db_path: str):
    """Verify capital_allocation.csv coverage vs the 92 companies in the DB."""
    logger.info("Running QA Gate on capital_allocation.csv...")
    try:
        csv_df = pd.read_csv("output/capital_allocation.csv")
    except FileNotFoundError:
        logger.warning("capital_allocation.csv not found in output/. Skipping QA gate.")
        return

    with sqlite3.connect(db_path) as conn:
        comp_df = pd.read_sql("SELECT id FROM companies", conn)

    expected_ids = set(comp_df["id"])
    found_ids = set(csv_df["company_id"])

    missing = expected_ids - found_ids
    if missing:
        logger.warning(
            f"QA Gate Failed: capital_allocation.csv is missing {len(missing)} companies out of 92."
        )
        logger.warning(f"Sample missing: {list(missing)[:5]}")
    else:
        logger.info(
            "QA Gate Passed: capital_allocation.csv has full 92 company coverage."
        )


def generate_report(db_path: str):
    logger.info("Connecting to database...")
    with sqlite3.connect(db_path) as conn:
        fr_df = pd.read_sql("SELECT * FROM financial_ratios WHERE year != 'TTM'", conn)
        comp_df = pd.read_sql("SELECT id, company_name FROM companies", conn)

    # 1. Distribution Summary (Latest Year)
    logger.info("Generating Distribution Summary...")
    fr_df["cal_year"] = fr_df["year"].apply(_extract_year)

    # Sort for latest year extraction
    fr_sorted = fr_df.sort_values(["company_id", "cal_year"])
    latest_df = fr_sorted.groupby("company_id").last().reset_index()

    # Fill NaN with NO_DATA to ensure we don't drop rows silently
    latest_df["cashflow_pattern_label"] = latest_df["cashflow_pattern_label"].fillna(
        "NO_DATA"
    )

    dist_summary = (
        latest_df.groupby("cashflow_pattern_label")
        .agg(
            count=("company_id", "count"),
            median_roe=("return_on_equity_pct", "median"),
            median_pat_cagr_5yr=("pat_cagr_5yr", "median"),
        )
        .reset_index()
    )

    # Ensure count is 92 (or valid companies count)
    total_count = dist_summary["count"].sum()
    logger.info(
        f"Distribution summary total count: {total_count} (expect {len(comp_df)})"
    )

    dist_summary = dist_summary.sort_values("count", ascending=False)

    os.makedirs("output", exist_ok=True)
    summary_file = "output/capital_allocation_summary.csv"
    dist_summary.to_csv(summary_file, index=False)
    logger.info(f"Saved summary to {summary_file}")

    # 2. YoY Pattern Change Detection
    logger.info("Detecting YoY Pattern Changes...")
    fr_sorted["prev_pattern"] = fr_sorted.groupby("company_id")[
        "cashflow_pattern_label"
    ].shift(1)
    fr_sorted["prev_year"] = fr_sorted.groupby("company_id")["year"].shift(1)
    fr_sorted["prev_cal_year"] = fr_sorted.groupby("company_id")["cal_year"].shift(1)

    # Calculate gap
    fr_sorted["year_gap"] = fr_sorted["cal_year"] - fr_sorted["prev_cal_year"]

    # Identify non-null transitions
    valid_transitions = fr_sorted[
        fr_sorted["prev_pattern"].notna() & fr_sorted["cashflow_pattern_label"].notna()
    ].copy()

    # Detect actual YoY changes vs Gaps
    # An actual change is where gap == 1 and pattern differs
    yoy_changes = valid_transitions[
        (valid_transitions["year_gap"] == 1)
        & (
            valid_transitions["cashflow_pattern_label"]
            != valid_transitions["prev_pattern"]
        )
    ]

    # Log non-standard gaps separately
    abnormal_gaps = valid_transitions[
        (valid_transitions["year_gap"] != 1)
        & (
            valid_transitions["cashflow_pattern_label"]
            != valid_transitions["prev_pattern"]
        )
    ]

    for _, row in abnormal_gaps.iterrows():
        logger.info(
            f"Gap != 1 pattern change detected for {row['company_id']}: {row['prev_year']} -> {row['year']} (gap: {row['year_gap']}). Not reporting in CSV."
        )

    changes_out = yoy_changes[
        ["company_id", "prev_year", "prev_pattern", "year", "cashflow_pattern_label"]
    ].copy()
    changes_out.columns = [
        "company_id",
        "prev_year",
        "prev_pattern",
        "latest_year",
        "latest_pattern",
    ]

    changes_file = "output/pattern_changes.csv"
    changes_out.to_csv(changes_file, index=False)
    logger.info(
        f"Saved {len(changes_out)} contiguous pattern changes to {changes_file}"
    )

    print("\n" + "=" * 60)
    print("DAY 32 \u2014 CAPITAL ALLOCATION REPORT \u2014 SUMMARY")
    print("=" * 60)
    print(f"  Distribution Total : {total_count}")
    print(
        f"  NO_DATA Count      : {int(dist_summary[dist_summary['cashflow_pattern_label'] == 'NO_DATA']['count'].sum())}"
    )
    print(f"  YoY Changes        : {len(changes_out)}")
    print("=" * 60)
    print("[DONE] Day 32 Complete")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    db_path = "db/nifty100.db"
    run_qa_gate(db_path)
    generate_report(db_path)
