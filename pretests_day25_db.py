import sqlite3
import pandas as pd
import os

DB_PATH = 'db/nifty100.db'

def run_pretests():
    print("--- Running Day 25 Pre-execution Verification ---")
    if not os.path.exists(DB_PATH):
        print(f"Error: Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    
    # 1. Partial History
    print("\n1. Partial History Check:")
    df_ratios = pd.read_sql("SELECT company_id, COUNT(*) as years FROM financial_ratios GROUP BY company_id", conn)
    partial = df_ratios[df_ratios['years'] < 5]
    print(f"Companies with < 5 years of financial_ratios data: {len(partial)}")
    if not partial.empty:
        print(partial.head())

    # 2. Missing Capital Allocation Labels
    print("\n2. Missing Capital Allocation Labels Check:")
    df_labels = pd.read_sql("SELECT company_id, cashflow_pattern_label, capex_intensity_label FROM financial_ratios WHERE year = (SELECT MAX(year) FROM financial_ratios)", conn)
    missing_cashflow = df_labels[df_labels['cashflow_pattern_label'].isna() | (df_labels['cashflow_pattern_label'] == '')]
    missing_capex = df_labels[df_labels['capex_intensity_label'].isna() | (df_labels['capex_intensity_label'] == '')]
    print(f"Companies missing cashflow_pattern_label: {len(missing_cashflow)}")
    print(f"Companies missing capex_intensity_label: {len(missing_capex)}")
    
    # 3. Zero/Null Market Cap
    print("\n3. Zero/Null Market Cap Check:")
    df_mc = pd.read_sql("SELECT * FROM market_cap WHERE year = (SELECT MAX(year) FROM market_cap)", conn)
    null_mc = df_mc[df_mc['market_cap_crore'].isna() | (df_mc['market_cap_crore'] <= 0)]
    print(f"Companies with NULL or <=0 market_cap_crore: {len(null_mc)}")
    
    # 4. Single-company sector
    print("\n4. Single-company Sector Check:")
    df_sectors = pd.read_sql("SELECT broad_sector, COUNT(*) as count FROM sectors GROUP BY broad_sector", conn)
    single_sectors = df_sectors[df_sectors['count'] == 1]
    print(f"Sectors with exactly 1 company: {len(single_sectors)}")
    if not single_sectors.empty:
        print(single_sectors)
        
    # 5. Negative values (PAT, Net Debt, FCF)
    print("\n5. Negative Values Check:")
    df_pl = pd.read_sql("SELECT company_id, net_profit FROM profitandloss", conn)
    neg_pat = df_pl[df_pl['net_profit'] < 0]
    print(f"Records with negative net_profit: {len(neg_pat)}")
    
    df_bs = pd.read_sql("SELECT company_id, borrowings FROM balancesheet", conn)
    neg_debt = df_bs[df_bs['borrowings'] < 0]
    print(f"Records with negative borrowings: {len(neg_debt)}")
    
    df_cf = pd.read_sql("SELECT company_id, free_cash_flow_cr FROM financial_ratios", conn)
    neg_fcf = df_cf[df_cf['free_cash_flow_cr'] < 0]
    print(f"Records with negative free_cash_flow_cr: {len(neg_fcf)}")

    conn.close()

if __name__ == "__main__":
    run_pretests()
