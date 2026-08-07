import os
import sys
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.screener.composite_score import compute_composite_score
from src.screener.engine import FilterEngine

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s"
)
logger = logging.getLogger("composite_all")


def main():
    db_path = "db/nifty100.db"

    # 1. Initialize engine to fetch full unfiltered universe DataFrame
    logger.info("Initializing ScreenerEngine to load full universe...")
    engine = FilterEngine(db_path, "config/screener_config.yaml")

    # 2. Extract the dataframe (92 companies)
    df = engine.df.copy()
    logger.info(f"Loaded {len(df)} companies.")

    # 3. Compute the 0-100 composite score
    logger.info("Computing composite score over the full universe...")
    scored_df = compute_composite_score(df, db_path)

    # 4. Filter strictly to company_id and screener_composite_score
    out_df = scored_df[["company_id", "screener_composite_score"]].copy()

    # 5. Export to CSV
    os.makedirs("output", exist_ok=True)
    out_path = "output/composite_scores_all.csv"
    out_df.to_csv(out_path, index=False)
    logger.info(f"Successfully generated {out_path} with {len(out_df)} rows.")


if __name__ == "__main__":
    main()
