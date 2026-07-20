import sqlite3
import pandas as pd


def run_review():
    conn = sqlite3.connect("db/nifty100.db")

    print("=== 5 Random Companies ===")
    comps = pd.read_sql(
        "SELECT id, company_name FROM companies ORDER BY RANDOM() LIMIT 5", conn
    )
    print(comps)

    print("\n=== Year Coverage ===")
    for _, row in comps.iterrows():
        cid = row["id"]
        y = pd.read_sql(
            f"SELECT year FROM profitandloss WHERE company_id='{cid}' ORDER BY year",
            conn,
        )
        print(f"{cid}: {y['year'].tolist()}")

    print("\n=== Companies with < 5 years of P&L ===")
    under_5 = pd.read_sql(
        "SELECT company_id, COUNT(*) as c FROM profitandloss GROUP BY company_id HAVING c < 5",
        conn,
    )
    print(under_5)


if __name__ == "__main__":
    run_review()
