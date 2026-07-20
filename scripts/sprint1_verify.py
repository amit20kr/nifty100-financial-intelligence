import sqlite3

conn = sqlite3.connect("db/nifty100.db")

print("=== SPRINT 1 EXIT CRITERIA VERIFICATION ===")
print("companies COUNT:", conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0])
print("PRAGMA FK check rows:", conn.execute("PRAGMA foreign_key_check").fetchall())

print("\n=== ORPHAN TICKER CLARIFICATION ===")
print(
    "ZOMATO in companies table:",
    conn.execute("SELECT COUNT(*) FROM companies WHERE id='ZOMATO'").fetchone()[0],
)
print(
    "WIPRO in companies table:",
    conn.execute("SELECT COUNT(*) FROM companies WHERE id='WIPRO'").fetchone()[0],
)
print(
    "VEDL in companies table:",
    conn.execute("SELECT COUNT(*) FROM companies WHERE id='VEDL'").fetchone()[0],
)
print(
    "TCS in companies table:",
    conn.execute("SELECT COUNT(*) FROM companies WHERE id='TCS'").fetchone()[0],
)
print(
    "INFY in companies table:",
    conn.execute("SELECT COUNT(*) FROM companies WHERE id='INFY'").fetchone()[0],
)

print("\n=== DISTINCT COMPANY COUNTS IN CHILD TABLES ===")
print(
    "distinct company_id in profitandloss:",
    conn.execute("SELECT COUNT(DISTINCT company_id) FROM profitandloss").fetchone()[0],
)
print(
    "distinct company_id in balancesheet:",
    conn.execute("SELECT COUNT(DISTINCT company_id) FROM balancesheet").fetchone()[0],
)
print(
    "distinct company_id in cashflow:",
    conn.execute("SELECT COUNT(DISTINCT company_id) FROM cashflow").fetchone()[0],
)
print(
    "distinct company_id in financial_ratios:",
    conn.execute("SELECT COUNT(DISTINCT company_id) FROM financial_ratios").fetchone()[
        0
    ],
)

print("\n=== JIOFIN COVERAGE CHECK (DQ-16 company) ===")
jiofin_rows = conn.execute(
    "SELECT year FROM profitandloss WHERE company_id='JIOFIN' ORDER BY year"
).fetchall()
print("JIOFIN years in profitandloss:", [r[0] for r in jiofin_rows])

print("\n=== SAMPLE ratio_engine cols check ===")
print(
    "financial_ratios columns:",
    [d[1] for d in conn.execute("PRAGMA table_info(financial_ratios)").fetchall()],
)
