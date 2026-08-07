import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def generate_valuation_reports(
    db_path: str = "db/nifty100.db", output_dir: str = "output"
):
    """
    Computes universe-wide valuation metrics and flags based on the anchor year.
    Generates valuation_summary.xlsx and valuation_flags.csv.
    """
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        # 1. Fetch Anchor Year Data
        # Same logic as engine.py to ensure FCF and Market Cap are perfectly aligned
        query_anchor = """
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
            c.id as company_id,
            c.company_name,
            s.broad_sector as sector,
            mc.pe_ratio,
            mc.pb_ratio,
            mc.ev_ebitda,
            mc.market_cap_crore,
            fr.free_cash_flow_cr
        FROM AnchorYear a
        JOIN companies c ON a.company_id = c.id
        JOIN financial_ratios fr ON a.company_id = fr.company_id AND a.year = fr.year
        LEFT JOIN market_cap mc ON a.company_id = mc.company_id AND a.year = mc.year
        LEFT JOIN sectors s ON a.company_id = s.company_id
        WHERE a.rn = 1;
        """
        df_base = pd.read_sql_query(query_anchor, conn)

        # 2. Compute 5-Year Median PE (Vectorized)
        query_5yr = """
        WITH Last5Years AS (
            SELECT 
                company_id, 
                pe_ratio,
                ROW_NUMBER() OVER(PARTITION BY company_id ORDER BY year DESC) as rn
            FROM market_cap
            WHERE pe_ratio > 0 AND pe_ratio IS NOT NULL
        )
        SELECT company_id, pe_ratio 
        FROM Last5Years 
        WHERE rn <= 5;
        """
        df_5yr = pd.read_sql_query(query_5yr, conn)

        # Calculate median only if n >= 3
        def get_median_if_valid(group):
            if len(group) >= 3:
                return group["pe_ratio"].median()
            return pd.NA

        median_5yr = (
            df_5yr.groupby("company_id")
            .apply(get_median_if_valid)
            .reset_index(name="5yr_median_PE")
        )
        df_base = df_base.merge(median_5yr, on="company_id", how="left")

    # 3. Compute Sector Median PE (from anchored year)
    # Filter valid PEs for sector calculation
    df_valid_pe = df_base[df_base["pe_ratio"] > 0]
    sector_medians = df_valid_pe.groupby("sector", as_index=False)["pe_ratio"].median()
    sector_medians.rename(columns={"pe_ratio": "sector_median_PE"}, inplace=True)

    df_base = df_base.merge(sector_medians, on="sector", how="left")

    # 4. Calculate Derived Metrics
    # FCF Yield
    df_base["FCF_yield_pct"] = (
        df_base["free_cash_flow_cr"] / df_base["market_cap_crore"]
    ) * 100

    # PE vs Sector Median Pct
    df_base["PE_vs_sector_median_pct"] = (
        (df_base["pe_ratio"] / df_base["sector_median_PE"]) - 1
    ) * 100

    # 5. Calculate Valuation Flags
    def evaluate_flag(row):
        pe = row["pe_ratio"]
        sec_med = row["sector_median_PE"]

        if pd.isna(pe) or pe <= 0 or pd.isna(sec_med):
            return "N/A"

        if pe > (sec_med * 1.5):
            return "Caution"
        elif pe < (sec_med * 0.7):
            return "Discount"
        else:
            return "Fair"

    df_base["flag"] = df_base.apply(evaluate_flag, axis=1)

    # Clean up and prepare outputs
    out_cols = [
        "company_id",
        "company_name",
        "sector",
        "pe_ratio",
        "pb_ratio",
        "ev_ebitda",
        "FCF_yield_pct",
        "5yr_median_PE",
        "PE_vs_sector_median_pct",
        "flag",
    ]

    df_summary = df_base[out_cols].copy()

    # Export Summary
    summary_path = os.path.join(output_dir, "valuation_summary.xlsx")
    df_summary.to_excel(summary_path, index=False)

    # Export Flags subset
    df_flags = df_summary[df_summary["flag"].isin(["Caution", "Discount"])].copy()
    flags_path = os.path.join(output_dir, "valuation_flags.csv")
    df_flags.to_csv(flags_path, index=False)

    print(f"Generated {summary_path} ({len(df_summary)} rows)")
    print(f"Generated {flags_path} ({len(df_flags)} rows)")


if __name__ == "__main__":
    generate_valuation_reports()
