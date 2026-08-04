import sqlite3
import pandas as pd

def run_pretests():
    conn = sqlite3.connect('db/nifty100.db')
    
    print("--- Pretest 1: market_cap row counts by company_id ---")
    df_counts = pd.read_sql("SELECT company_id, COUNT(*) as years_count FROM market_cap GROUP BY company_id", conn)
    short_history = df_counts[df_counts['years_count'] < 5]
    print(f"Companies with < 5 years of history: {len(short_history)}")
    print(short_history.head(10))
    
    print("\n--- Pretest 2: financial_ratios vs market_cap mismatch ---")
    # Identify anchor year logic mismatch
    query_mismatch = """
    SELECT r.company_id, r.year as ratio_year, m.year as mc_year 
    FROM financial_ratios r 
    LEFT JOIN market_cap m ON r.company_id = m.company_id AND r.year = m.year
    WHERE m.year IS NULL
    """
    df_mismatch = pd.read_sql(query_mismatch, conn)
    print(f"Total mismatch rows: {len(df_mismatch)}")
    print(df_mismatch.head(5))
    
    print("\n--- Pretest 3: pe_ratio / market_cap_crore NULL or <= 0 ---")
    query_invalid = """
    SELECT company_id, year, pe_ratio, market_cap_crore
    FROM market_cap
    WHERE pe_ratio IS NULL OR pe_ratio <= 0
       OR market_cap_crore IS NULL OR market_cap_crore <= 0
    """
    df_invalid = pd.read_sql(query_invalid, conn)
    print(f"Rows with invalid PE or Market Cap: {len(df_invalid)}")
    print(df_invalid.head(5))
    
    print("\n--- Pretest 4: Sector valid P/E coverage ---")
    query_sector = """
    WITH LatestYear AS (
        SELECT company_id, MAX(year) as max_year
        FROM market_cap
        GROUP BY company_id
    )
    SELECT s.broad_sector, COUNT(m.pe_ratio) as valid_pe_count
    FROM sectors s
    JOIN LatestYear ly ON s.company_id = ly.company_id
    JOIN market_cap m ON ly.company_id = m.company_id AND ly.max_year = m.year
    WHERE m.pe_ratio > 0 AND m.pe_ratio IS NOT NULL
    GROUP BY s.broad_sector
    """
    df_sector = pd.read_sql(query_sector, conn)
    empty_sectors = df_sector[df_sector['valid_pe_count'] == 0]
    print(f"Sectors with 0 valid P/Es in latest year: {len(empty_sectors)}")
    if len(empty_sectors) > 0:
        print(empty_sectors)
    else:
        print("All sectors have at least one valid P/E.")

    print("\n--- Pretest 5: Spot check RELIANCE and JIOFIN ---")
    df_spot = pd.read_sql("SELECT company_id, year, pe_ratio, market_cap_crore FROM market_cap WHERE company_id IN ('RELIANCE', 'JIOFIN') ORDER BY company_id, year DESC", conn)
    print(df_spot)
    
if __name__ == '__main__':
    run_pretests()
