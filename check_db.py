import sqlite3
import pandas as pd

conn = sqlite3.connect("db/nifty100.db")
df = pd.read_sql_query(
    "SELECT year, return_on_equity_pct, return_on_capital_employed_pct, net_profit_margin_pct, debt_to_equity, revenue_cagr_5yr, free_cash_flow_cr FROM financial_ratios WHERE company_id = 'RELIANCE' ORDER BY year DESC LIMIT 5",
    conn,
)
print(df)
conn.close()
