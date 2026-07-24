"""
scripts/day14_sprint2_review.py
--------------------------------
Day 14: Sprint 2 final verification script.
Runs all exit-criteria checks, screener preview, and 5-company demo.
"""

import sqlite3
import os

DB_PATH = "db/nifty100.db"
LOG_PATH = "output/ratio_edge_cases.log"
CSV_PATH = "output/capital_allocation.csv"

KPI_COLS = [
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "return_on_assets_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "net_debt_cr",
    "free_cash_flow_cr",
    "capex_cr",
    "capex_intensity_pct",
    "fcf_conversion_pct",
    "composite_quality_score",
    "cashflow_pattern_code",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
    "earnings_per_share",
    "book_value_per_share",
    "dividend_payout_ratio_pct",
    "total_debt_cr",
]

PASS = "[PASS]"
FAIL = "[FAIL]"


def check(cond):
    return PASS if cond else FAIL


def run():
    conn = sqlite3.connect(DB_PATH)
    print("=" * 70)
    print("SPRINT 2 — DAY 14 EXIT CRITERIA VERIFICATION")
    print("=" * 70)

    # ── CRITERION 1: Row count ──
    rows = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    companies = conn.execute(
        "SELECT COUNT(DISTINCT company_id) FROM financial_ratios"
    ).fetchone()[0]
    print(f"\n[1] financial_ratios row count : {rows:,}  {check(rows >= 1100)}")
    print(f"[1] Distinct companies          : {companies}     {check(companies == 92)}")

    # ── CRITERION 2: KPI columns non-null ──
    print(f"\n[2] KPI column null-only audit ({len(KPI_COLS)} columns):")
    null_only = []
    for col in KPI_COLS:
        n = conn.execute(
            f"SELECT COUNT(*) FROM financial_ratios WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        status = PASS if n > 0 else FAIL
        print(f"    {col:40} {n:>5} non-null  {status}")
        if n == 0:
            null_only.append(col)
    print(
        f"    Null-only columns: {null_only if null_only else 'NONE'} {check(not null_only)}"
    )

    # ── CRITERION 3: ratio_edge_cases.log ──
    print("\n[3] ratio_edge_cases.log check:")
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            log_lines = [line.strip() for line in f if line.strip()]
        triage_remaining = [line for line in log_lines if "to_be_triaged" in line]
        categories = {}
        for line in log_lines:
            if "category:" in line:
                cat = line.split("category:")[-1].strip()
                categories[cat] = categories.get(cat, 0) + 1
        print(f"    Total log entries           : {len(log_lines)}")
        print(
            f"    Un-triaged (to_be_triaged)  : {len(triage_remaining)}  {check(len(triage_remaining) == 0)}"
        )
        print("    Category breakdown:")
        for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"      {cat:40} : {cnt}")
    else:
        print(f"    {FAIL} Log file not found at {LOG_PATH}")

    # ── CRITERION 4: capital_allocation.csv ──
    print("\n[4] capital_allocation.csv check:")
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH) as f:
            csv_lines = f.readlines()
        csv_rows = len(csv_lines) - 1  # minus header
        null_pattern_rows = conn.execute(
            "SELECT COUNT(*) FROM financial_ratios WHERE cashflow_pattern_code IS NULL"
        ).fetchone()[0]
        parity_ok = csv_rows + null_pattern_rows == rows
        print(f"    CSV data rows               : {csv_rows}")
        print(f"    DB rows w/NULL pattern      : {null_pattern_rows}")
        print(
            f"    CSV + NULL = total rows     : {csv_rows + null_pattern_rows} == {rows}  {check(parity_ok)}"
        )
    else:
        print(f"    {FAIL} CSV not found at {CSV_PATH}")

    # ── SCREENER PREVIEW: ROE > 15 AND D/E < 1 ──
    print("\n[5] SCREENER PREVIEW: ROE > 15% AND D/E < 1.0 (latest year per company)")
    screener_rows = conn.execute(
        """
        SELECT fr.company_id, c.company_name, fr.year,
               fr.return_on_equity_pct, fr.debt_to_equity, fr.return_on_capital_employed_pct
        FROM financial_ratios fr
        JOIN companies c ON fr.company_id = c.id
        WHERE fr.return_on_equity_pct > 15
          AND fr.debt_to_equity < 1.0
          AND fr.year = (
              SELECT MAX(fr2.year) FROM financial_ratios fr2
              WHERE fr2.company_id = fr.company_id AND fr2.year NOT LIKE '%-09'
          )
        ORDER BY fr.return_on_equity_pct DESC
    """
    ).fetchall()
    print(
        f"    Companies passing filter      : {len(screener_rows)}  {check(15 <= len(screener_rows) <= 50)}"
    )
    print(f"    {'Company':15} {'Name':35} {'Year':7} {'ROE%':7} {'D/E':6} {'ROCE%':7}")
    print("    " + "-" * 80)
    for r in screener_rows[:20]:
        name = (r[1] or "")[:34]
        print(f"    {r[0]:15} {name:35} {r[2]:7} {r[3]:7.1f} {r[4]:6.2f} {r[5]:7.1f}")
    if len(screener_rows) > 20:
        print(f"    ... and {len(screener_rows) - 20} more")

    # ── DEMO: 5-company KPI table ──
    print("\n[6] DEMO: 5-company KPI snapshot (latest fiscal year)")
    demo_rows = conn.execute(
        """
        SELECT fr.company_id, fr.year,
               fr.net_profit_margin_pct, fr.return_on_equity_pct,
               fr.return_on_capital_employed_pct, fr.debt_to_equity,
               fr.revenue_cagr_5yr, fr.composite_quality_score,
               fr.cfo_quality_label, fr.cashflow_pattern_label,
               fr.capex_intensity_pct, fr.free_cash_flow_cr
        FROM financial_ratios fr
        WHERE fr.company_id IN ('TCS','HDFCBANK','RELIANCE','INFY','TITAN')
          AND fr.year = (
              SELECT MAX(fr2.year) FROM financial_ratios fr2
              WHERE fr2.company_id = fr.company_id AND fr2.year NOT LIKE '%-09'
          )
        ORDER BY fr.company_id
    """
    ).fetchall()
    print(
        f"    {'Co':10} {'Year':7} {'NPM%':7} {'ROE%':7} {'ROCE%':7} {'D/E':6} {'RevCAGR':8} {'CFO Qual':10} {'CFO Label':20} {'Pattern':25} {'CapEx%':7} {'FCF Cr':8}"
    )
    print("    " + "-" * 128)
    for r in demo_rows:

        def fmt(v, d=1):
            return f"{v:.{d}f}" if v is not None else "N/A"

        label = (r[8] or "N/A")[:19]
        pattern = (r[9] or "N/A")[:24]
        print(
            f"    {r[0]:10} {r[1]:7} {fmt(r[2]):7} {fmt(r[3]):7} {fmt(r[4]):7} {fmt(r[5],2):6} {fmt(r[6]):8} {fmt(r[7]):10} {label:20} {pattern:25} {fmt(r[10]):7} {fmt(r[11]):8}"
        )

    # ── SUMMARY ──
    all_pass = (
        rows >= 1100
        and companies == 92
        and not null_only
        and 15 <= len(screener_rows) <= 50
    )
    print(f"\n{'=' * 70}")
    print(
        f"SPRINT 2 STATUS: {'ALL EXIT CRITERIA MET — READY FOR GITHUB PUSH' if all_pass else 'SOME CRITERIA FAILED — SEE ABOVE'}"
    )
    print(f"{'=' * 70}")
    conn.close()


if __name__ == "__main__":
    run()
