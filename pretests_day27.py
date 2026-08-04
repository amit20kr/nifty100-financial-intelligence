import sqlite3
import pandas as pd
import json
import time

def run_pretests():
    # 1. Prosandcons count
    conn = sqlite3.connect('db/nifty100.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT company_id) FROM prosandcons")
    pros_count = cursor.fetchone()[0]
    missing_pros = 92 - pros_count
    print(f"Companies WITH pros/cons: {pros_count}")
    print(f"Companies MISSING pros/cons: {missing_pros} / 92")
    
    # 2. Test pd.NA formatting
    def fmt(v, suffix=""):
        return f"{v:.2f}{suffix}" if pd.notna(v) else "N/A"
    
    try:
        val = pd.NA
        res = fmt(val)
        print(f"fmt(pd.NA) result: {res}")
    except BaseException as e:
        print(f"fmt(pd.NA) failed: {type(e).__name__} - {e}")
        
    # 3. Dry run filter engine extreme values
    from src.screener.engine import FilterEngine
    from pathlib import Path
    try:
        engine = FilterEngine(Path("db/nifty100.db"), Path("config/screener_config.yaml"))
        payload = {
            "return_on_equity_pct": -20.0,
            "pe_ratio": 150.0,
            "free_cash_flow_cr": -5000.0,
            "debt_to_equity": 0.0, # test financials bypass
            "interest_coverage": -5.0 # test icr infinity bypass
        }
        res = engine.apply(payload)
        print(f"Stress test dry run rows returned: {len(res)}")
    except Exception as e:
        print(f"Stress test dry run failed: {e}")

if __name__ == '__main__':
    run_pretests()
