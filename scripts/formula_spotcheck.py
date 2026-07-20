import sqlite3

conn = sqlite3.connect("db/nifty100.db")

print("=== TCS 2024-03 P&L (for manual formula spot-check) ===")
row = conn.execute(
    "SELECT company_id, year, sales, operating_profit, opm_percentage, "
    "profit_before_tax, interest, net_profit, eps FROM profitandloss "
    "WHERE company_id='TCS' AND year='2024-03'"
).fetchone()
print(row)

print("\n=== TCS 2024-03 Balance Sheet ===")
bs = conn.execute(
    "SELECT company_id, year, equity_capital, reserves, borrowings, total_assets "
    "FROM balancesheet WHERE company_id='TCS' AND year='2024-03'"
).fetchone()
print(bs)

print("\n=== HDFCBANK 2024-03 P&L (BFSI sample for ROCE sector_category check) ===")
row2 = conn.execute(
    "SELECT company_id, year, sales, operating_profit, opm_percentage, "
    "profit_before_tax, interest, net_profit FROM profitandloss "
    "WHERE company_id='HDFCBANK' AND year='2024-03'"
).fetchone()
print(row2)

print("\n=== HDFCBANK 2024-03 Balance Sheet ===")
bs2 = conn.execute(
    "SELECT company_id, year, equity_capital, reserves, borrowings, total_assets "
    "FROM balancesheet WHERE company_id='HDFCBANK' AND year='2024-03'"
).fetchone()
print(bs2)

print("\n=== JIOFIN rows (partial history company) ===")
rows = conn.execute(
    "SELECT company_id, year, sales, net_profit FROM profitandloss "
    "WHERE company_id='JIOFIN' ORDER BY year"
).fetchall()
for r in rows:
    print(r)

# Manual formula verification for TCS
if row and bs:
    sales, op, opm_pct, pbt, interest, np_ = (
        row[2],
        row[3],
        row[4],
        row[5],
        row[6],
        row[7],
    )
    eq, res, borrow, ta = bs[2], bs[3], bs[4], bs[5]
    print("\n=== MANUAL FORMULA VERIFICATION (TCS 2024-03) ===")
    npm = round(np_ / sales * 100, 4) if sales else None
    opm = round(op / sales * 100, 4) if sales else None
    roe_denom = (eq or 0) + (res or 0)
    roe = round(np_ / roe_denom * 100, 4) if roe_denom > 0 else None
    ebit = (pbt or 0) + (interest or 0)
    roce_denom = (eq or 0) + (res or 0) + (borrow or 0)
    roce = round(ebit / roce_denom * 100, 4) if roce_denom > 0 else None
    roa = round(np_ / ta * 100, 4) if ta else None
    print(f"NPM  = {np_} / {sales} * 100 = {npm}")
    print(
        f'OPM  = {op} / {sales} * 100 = {opm} (source opm_pct = {opm_pct}, diff = {round(abs(opm - opm_pct), 4) if opm else "N/A"})'
    )
    print(f"ROE  = {np_} / ({eq} + {res}) * 100 = {roe}")
    print(f"EBIT = {pbt} + {interest} = {ebit}")
    print(f"ROCE = {ebit} / ({eq} + {res} + {borrow}) * 100 = {roce}")
    print(f"ROA  = {np_} / {ta} * 100 = {roa}")
