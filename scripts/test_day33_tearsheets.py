import os
import sys
import sqlite3
import pandas as pd
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.reports.tearsheet import TearsheetGenerator, InsufficientDataError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s"
)
logger = logging.getLogger("test_tearsheets")


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

    generator = TearsheetGenerator(
        df_comp, df_fr, df_cf, df_pl, df_bs, df_pc, df_ci, df_comp_score
    )

    test_companies = [
        "TCS",
        "HDFCBANK",
        "RELIANCE",
        "SUNPHARMA",
        "TATASTEEL",
        "ICICIBANK",
    ]

    os.makedirs("reports/tearsheets", exist_ok=True)

    for cid in test_companies:
        out_path = f"reports/tearsheets/{cid}_tearsheet.pdf"
        try:
            logger.info(f"Generating tearsheet for {cid}...")
            generator.generate(cid, out_path)
            logger.info(f"Successfully generated {out_path}")
        except InsufficientDataError as e:
            logger.warning(f"Skipping {cid}: {e}")
        except Exception as e:
            logger.error(f"Failed to generate tearsheet for {cid}: {e}", exc_info=True)


if __name__ == "__main__":
    main()
