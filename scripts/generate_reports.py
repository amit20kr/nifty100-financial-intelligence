import os
import sys
import sqlite3
import pandas as pd
import logging
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.reports.tearsheet import TearsheetGenerator, InsufficientDataError
from src.reports.sector_report import SectorReportGenerator

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s"
)
logger = logging.getLogger("batch_reports")


def main():
    db_path = "db/nifty100.db"
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        sys.exit(1)

    logger.info("Pre-loading dataframes from database and CSVs...")
    with sqlite3.connect(db_path) as conn:
        df_comp = pd.read_sql("SELECT * FROM companies", conn)
        df_fr = pd.read_sql("SELECT * FROM financial_ratios", conn)
        df_cf = pd.read_sql("SELECT * FROM cashflow", conn)
        df_pl = pd.read_sql("SELECT * FROM profitandloss", conn)
        df_bs = pd.read_sql("SELECT * FROM balancesheet", conn)
        df_mc = pd.read_sql("SELECT * FROM market_cap", conn)

    try:
        df_pc = pd.read_csv("output/pros_cons_generated.csv")
    except FileNotFoundError:
        df_pc = pd.DataFrame()

    try:
        df_ci = pd.read_excel("output/cashflow_intelligence.xlsx")
    except FileNotFoundError:
        df_ci = pd.DataFrame()

    try:
        df_comp_score = pd.read_csv("output/composite_scores_all.csv")
    except FileNotFoundError:
        df_comp_score = pd.DataFrame()

    # Read env threshold
    min_years_env = os.getenv("TEARSHEET_MIN_YEARS", "3")
    try:
        min_years = int(min_years_env)
    except:
        min_years = 3

    tearsheet_gen = TearsheetGenerator(
        df_comp, df_fr, df_cf, df_pl, df_bs, df_pc, df_ci, df_comp_score, df_mc
    )
    sector_gen = SectorReportGenerator(df_comp, df_fr, df_ci, df_comp_score, df_mc)

    out_dir_ts = "reports/tearsheets"
    out_dir_sec = "reports/sector"
    os.makedirs(out_dir_ts, exist_ok=True)
    os.makedirs(out_dir_sec, exist_ok=True)

    skipped = []
    errors = []

    logger.info(f"Starting batch tearsheet generation (min_years={min_years})...")

    for _, row in df_comp.iterrows():
        cid = row["id"]
        cname = row["company_name"]

        # Check min years against both PL and FR
        pl_sub = df_pl[(df_pl["company_id"] == cid) & (df_pl["year"] != "TTM")]
        fr_sub = df_fr[(df_fr["company_id"] == cid) & (df_fr["year"] != "TTM")]

        pl_years = len(pl_sub)
        fr_years = len(fr_sub)

        if min(pl_years, fr_years) < min_years:
            reason = f"pl_years={pl_years}, fr_years={fr_years} < {min_years}"
            logger.info(f"Skipping {cid}: {reason}")
            skipped.append(
                {
                    "company_id": cid,
                    "company_name": cname,
                    "profitandloss_years": pl_years,
                    "financial_ratios_years": fr_years,
                    "reason": reason,
                }
            )
            continue

        out_path = os.path.join(out_dir_ts, f"{cid}_tearsheet.pdf")

        try:
            tearsheet_gen.generate(cid, out_path)
            logger.debug(f"Generated {out_path}")
        except InsufficientDataError as e:
            reason = str(e)
            logger.info(f"Skipping {cid} inside generator: {reason}")
            skipped.append(
                {
                    "company_id": cid,
                    "company_name": cname,
                    "profitandloss_years": pl_years,
                    "financial_ratios_years": fr_years,
                    "reason": reason,
                }
            )
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to generate tearsheet for {cid}: {err_msg}")
            errors.append(
                {
                    "company_id": cid,
                    "error": err_msg,
                    "traceback": traceback.format_exc(),
                }
            )

    # Export skipped
    if skipped:
        pd.DataFrame(skipped).to_csv("output/skipped_tearsheets.csv", index=False)
        logger.info(
            f"Exported {len(skipped)} skipped records to output/skipped_tearsheets.csv"
        )
    else:
        # Create empty with schema
        pd.DataFrame(
            columns=[
                "company_id",
                "company_name",
                "profitandloss_years",
                "financial_ratios_years",
                "reason",
            ]
        ).to_csv("output/skipped_tearsheets.csv", index=False)

    # Export errors
    if errors:
        pd.DataFrame(errors).to_csv(
            "output/tearsheet_generation_errors.csv", index=False
        )
        logger.warning(
            f"Exported {len(errors)} error records to output/tearsheet_generation_errors.csv"
        )
    else:
        # Empty schema
        pd.DataFrame(columns=["company_id", "error", "traceback"]).to_csv(
            "output/tearsheet_generation_errors.csv", index=False
        )

    # Sector reports
    logger.info("Starting batch sector report generation...")
    sector_gen.generate_all(out_dir_sec)

    logger.info("Day 34 Batch Generation Complete!")


if __name__ == "__main__":
    main()
