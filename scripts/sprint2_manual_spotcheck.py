"""
scripts/sprint2_manual_spotcheck.py
-----------------------------------
Sprint 2 Manual Spot-check for ROE and 5-year Revenue CAGR for TCS, RELIANCE, and INFY.
"""

import sqlite3
import os

DB_PATH = "db/nifty100.db"


def run_spotcheck():
    if not os.path.exists(DB_PATH):
        DB_PATH_ABS = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "db", "nifty100.db"
        )
        conn = sqlite3.connect(DB_PATH_ABS)
    else:
        conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    companies = ["TCS", "RELIANCE", "INFY"]
    year_end = "2024-03"
    year_start = "2019-03"

    print("=" * 110)
    print("SPRINT 2 MANUAL SPOT-CHECK: ROE & 5-YEAR REVENUE CAGR (2024-03)")
    print("=" * 110)

    all_passed = True

    print("\n[1] ROE MANUAL COMPUTATION (Year: 2024-03)")
    print(
        f"{'Company':<10} | {'Net Profit':<12} | {'Equity Cap':<12} | {'Reserves':<12} | {'Manual ROE (%)':<14} | {'Engine ROE (%)':<14} | {'Abs Diff (%)':<12} | {'Status':<6}"
    )
    print("-" * 110)

    for comp in companies:
        cursor.execute(
            "SELECT net_profit FROM profitandloss WHERE company_id = ? AND year = ?",
            (comp, year_end),
        )
        np_row = cursor.fetchone()
        net_profit = np_row[0] if np_row else None

        cursor.execute(
            "SELECT equity_capital, reserves FROM balancesheet WHERE company_id = ? AND year = ?",
            (comp, year_end),
        )
        bs_row = cursor.fetchone()
        equity_cap = bs_row[0] if bs_row else None
        reserves = bs_row[1] if bs_row else None

        cursor.execute(
            "SELECT return_on_equity_pct FROM financial_ratios WHERE company_id = ? AND year = ?",
            (comp, year_end),
        )
        fr_row = cursor.fetchone()
        engine_roe = fr_row[0] if fr_row else None

        denom = (equity_cap or 0) + (reserves or 0)
        manual_roe = (
            (net_profit / denom * 100.0)
            if denom > 0 and net_profit is not None
            else None
        )

        if manual_roe is not None and engine_roe is not None:
            abs_diff_roe = abs(manual_roe - engine_roe)
            pass_roe = abs_diff_roe < 0.1
        else:
            abs_diff_roe = None
            pass_roe = False

        if not pass_roe:
            all_passed = False

        status_str = "PASS" if pass_roe else "FAIL"

        print(
            f"{comp:<10} | {net_profit:<12.2f} | {equity_cap:<12.2f} | {reserves:<12.2f} | {manual_roe:<14.4f} | {engine_roe:<14.4f} | {abs_diff_roe:<12.4f} | {status_str:<6}"
        )

    print("\n[2] 5-YEAR REVENUE CAGR MANUAL COMPUTATION (2019-03 to 2024-03)")
    print(
        f"{'Company':<10} | {'Sales 2019':<12} | {'Sales 2024':<12} | {'Manual CAGR (%)':<15} | {'Engine CAGR (%)':<15} | {'Abs Diff (%)':<12} | {'Status':<6}"
    )
    print("-" * 110)

    for comp in companies:
        cursor.execute(
            "SELECT sales FROM profitandloss WHERE company_id = ? AND year = ?",
            (comp, year_start),
        )
        s19_row = cursor.fetchone()
        sales_2019 = s19_row[0] if s19_row else None

        cursor.execute(
            "SELECT sales FROM profitandloss WHERE company_id = ? AND year = ?",
            (comp, year_end),
        )
        s24_row = cursor.fetchone()
        sales_2024 = s24_row[0] if s24_row else None

        cursor.execute(
            "SELECT revenue_cagr_5yr FROM financial_ratios WHERE company_id = ? AND year = ?",
            (comp, year_end),
        )
        fr_cagr_row = cursor.fetchone()
        engine_cagr = fr_cagr_row[0] if fr_cagr_row else None

        if sales_2019 and sales_2024 and sales_2019 > 0:
            manual_cagr = ((sales_2024 / sales_2019) ** (1.0 / 5.0) - 1.0) * 100.0
        else:
            manual_cagr = None

        if manual_cagr is not None and engine_cagr is not None:
            abs_diff_cagr = abs(manual_cagr - engine_cagr)
            pass_cagr = abs_diff_cagr < 0.1
        else:
            abs_diff_cagr = None
            pass_cagr = False

        if not pass_cagr:
            all_passed = False

        status_str = "PASS" if pass_cagr else "FAIL"

        print(
            f"{comp:<10} | {sales_2019:<12.2f} | {sales_2024:<12.2f} | {manual_cagr:<15.4f} | {engine_cagr:<15.4f} | {abs_diff_cagr:<12.4f} | {status_str:<6}"
        )

    print("\n" + "=" * 110)
    if all_passed:
        print("SUMMARY: ALL 6 CHECKS PASSED (Absolute diff < 0.1%)")
    else:
        print("SUMMARY: ONE OR MORE CHECKS FAILED")
    print("=" * 110)

    conn.close()


if __name__ == "__main__":
    run_spotcheck()
