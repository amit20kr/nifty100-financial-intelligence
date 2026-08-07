import sqlite3
import pandas as pd
import os
from src.analytics.cagr import calculate_cagr, extract_cagr_window


def generate_cagr_full():
    os.makedirs("output", exist_ok=True)
    with sqlite3.connect("db/nifty100.db") as conn:
        pl_df = pd.read_sql_query("SELECT * FROM profitandloss", conn)
        companies = pd.read_sql_query("SELECT id, company_name FROM companies", conn)

    records = []

    for _, comp in companies.iterrows():
        cid = comp["id"]
        cname = comp["company_name"]
        c_series = pl_df[pl_df["company_id"] == cid].copy()

        row = {"company_id": cid, "company_name": cname}

        for metric in ["sales", "net_profit", "eps"]:
            for window in [3, 5, 10]:
                start, end, yrs, insuf = extract_cagr_window(c_series, window, metric)
                res = calculate_cagr(start, end, yrs, insuf)

                val_key = f"{metric}_{window}yr_cagr"
                flag_key = f"{metric}_{window}yr_flag"

                row[val_key] = res.value
                row[flag_key] = res.flag.value if res.flag else None

        records.append(row)

    out_df = pd.DataFrame(records)
    out_df.to_csv("output/cagr_full.csv", index=False)
    print("Generated output/cagr_full.csv")


if __name__ == "__main__":
    generate_cagr_full()
