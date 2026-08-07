import os
import sys
import sqlite3
import pandas as pd
import logging

from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.nlp.pros_cons_generator import generate_pros_cons

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("day30_pros_cons")


def main():
    load_dotenv()

    db_path = "db/nifty100.db"
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        sys.exit(1)

    logger.info(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)

    # Get total companies for validation
    comp_df = pd.read_sql("SELECT id FROM companies", conn)
    total_companies = len(comp_df)
    logger.info(f"Loaded {total_companies} companies.")

    logger.info("Running Pros/Cons Generator (24 rules)...")
    res_df = generate_pros_cons(conn)

    if res_df.empty:
        logger.error("Generator returned empty DataFrame!")
        sys.exit(1)

    total_rules_triggered = len(res_df)
    pro_count = len(res_df[res_df["type"] == "pro"])
    con_count = len(res_df[res_df["type"] == "con"])

    logger.info(
        f"Generated {total_rules_triggered} total insights ({pro_count} Pros, {con_count} Cons)"
    )

    # Gap Validation
    comp_pros = res_df[res_df["type"] == "pro"].groupby("company_id").size()
    comp_cons = res_df[res_df["type"] == "con"].groupby("company_id").size()

    zero_pros = [c for c in comp_df["id"] if c not in comp_pros.index]
    zero_cons = [c for c in comp_df["id"] if c not in comp_cons.index]

    if zero_pros or zero_cons:
        logger.warning(
            f"Gaps detected \u2014 zero_pros: {len(zero_pros)}, zero_cons: {len(zero_cons)}"
        )
        gaps = []
        fr_df = pd.read_sql("SELECT * FROM financial_ratios WHERE year != 'TTM'", conn)
        for c in zero_pros:
            gaps.append(
                {"company_id": c, "missing": "pro", "reason": "no_rule_triggered"}
            )
        for c in zero_cons:
            c_fr = fr_df[fr_df["company_id"] == c]
            if c_fr.empty:
                reason = "insufficient_data"
            else:
                latest = c_fr.iloc[-1]
                if pd.isna(latest.get("return_on_capital_employed_pct")) and pd.isna(
                    latest.get("operating_profit_margin_pct")
                ):
                    reason = "insufficient_data"
                else:
                    reason = "no_rule_triggered"
            gaps.append({"company_id": c, "missing": "con", "reason": reason})
        gap_df = pd.DataFrame(gaps)
        os.makedirs("output", exist_ok=True)
        gap_file = "output/pros_cons_coverage_gaps.csv"
        gap_df.to_csv(gap_file, index=False)
        logger.warning(f"Gaps logged to {gap_file}")
    else:
        # Write an empty gaps file so downstream checks know we ran cleanly
        pd.DataFrame(columns=["company_id", "missing", "reason"]).to_csv(
            "output/pros_cons_coverage_gaps.csv", index=False
        )
        logger.info(
            "All 92 companies have at least 1 pro and 1 con. Exit criterion PASSED."
        )

    # Success Path — write output regardless of residual gap warnings
    os.makedirs("output", exist_ok=True)

    out_file = "output/pros_cons_generated.csv"
    res_df.to_csv(out_file, index=False)

    logger.info(f"Successfully wrote {out_file}")

    print("\n" + "=" * 60)
    print("DAY 30 \u2014 NLP PROS/CONS GENERATOR \u2014 SUMMARY")
    print("=" * 60)
    print(f"  Companies Evaluated : {total_companies}")
    print(f"  Total Rules Triggered : {total_rules_triggered}")
    print(f"    +-- Pros : {pro_count}")
    print(f"    +-- Cons : {con_count}")
    print(
        f"\n  Average Insights per Company : {total_rules_triggered / total_companies:.1f}"
    )
    print(f"  Zero-hit coverage gaps : {len(zero_pros) + len(zero_cons)}")
    print("=" * 60)
    print("[DONE] Day 30 Complete")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
