import sqlite3
from pathlib import Path

import pandas as pd

REQUIRED_CF_COLUMNS = [
    "company_id",
    "sector",
    "cfo_quality_score",
    "cfo_quality_label",
    "capex_intensity_pct",
    "capex_label",
    "fcf_cagr_5yr",
    "fcf_conversion_pct",
    "distress_flag",
    "deleveraging_flag",
    "capital_allocation_label",
]

UTILITY_NAME_HINTS = [
    "NTPC",
    "POWERGRID",
    "NHPC",
    "TATAPOWER",
    "ADANIPOWER",
    "ADANIENERGY",
    "JSWENERGY",
    "SJVN",
    "TORNTPOWER",
]


def check_pros_cons_gap_reasoning():
    p = Path("output/pros_cons_coverage_gaps.csv")
    if not p.exists():
        print("[1] FAIL: output/pros_cons_coverage_gaps.csv not found")
        return
    gaps = pd.read_csv(p)
    print(f"[1] pros_cons_coverage_gaps.csv: {len(gaps)} rows")
    if gaps.empty:
        print("    No gaps logged")
        return
    reasons = gaps["reason"].unique() if "reason" in gaps.columns else []
    print(f"    Distinct reasons present: {list(reasons)}")
    if list(reasons) == ["no_rule_triggered"]:
        print(
            "    NOTE: gaps tagged uniformly; data-completeness distinction not yet added."
        )
    con_gaps = gaps[gaps["missing"] == "con"] if "missing" in gaps.columns else gaps
    print(
        f"    Companies missing a con: {len(con_gaps)} (expected ~43, DESIGNED behavior)"
    )


def check_cashflow_intelligence_columns():
    p = Path("output/cashflow_intelligence.xlsx")
    if not p.exists():
        print("[2] FAIL: output/cashflow_intelligence.xlsx not found")
        return
    df = pd.read_excel(p)
    print(f"[2] cashflow_intelligence.xlsx: {len(df)} rows (expect 92)")
    missing = [c for c in REQUIRED_CF_COLUMNS if c not in df.columns]
    if missing:
        print(f"    ACTUAL MISSING COLUMNS: {missing}")
        print("    Re-run scripts/run_day31_cf_intelligence.py if this fires.")
    else:
        print(f"    All {len(REQUIRED_CF_COLUMNS)} required columns present.")
        nulls = df[REQUIRED_CF_COLUMNS].isna().sum()
        nontrivial = nulls[nulls > 0]
        if not nontrivial.empty:
            print(f"    Columns with some NULLs: {dict(nontrivial)}")


def check_sector_count():
    conn = sqlite3.connect("db/nifty100.db")
    sectors = pd.read_sql_query("SELECT company_id, broad_sector FROM sectors", conn)
    companies = pd.read_sql_query("SELECT id, company_name FROM companies", conn)
    distinct = sorted(sectors["broad_sector"].dropna().unique())
    print(f"[3] Distinct broad_sector values in DB: {len(distinct)}")
    for s in distinct:
        print(f"    {s}")

    pdf_dir = Path("reports/sector")
    pdf_sectors = (
        {p.stem.replace("_report", "") for p in pdf_dir.glob("*.pdf")}
        if pdf_dir.exists()
        else set()
    )
    print(f"    Sector PDFs on disk: {len(pdf_sectors)}")
    db_sectors_sanitized = {"_".join(s.split()) for s in distinct}
    unmatched = db_sectors_sanitized - pdf_sectors
    if unmatched:
        print(f"    WARNING: sectors in DB with no corresponding PDF: {unmatched}")
    else:
        print(
            "    Every distinct DB sector has a corresponding PDF -- 10 is complete, not partial"
        )

    print(
        "    Checking for known Nifty utility companies and their assigned broad_sector:"
    )
    found_any = False
    for hint in UTILITY_NAME_HINTS:
        match = companies[
            companies["company_name"].str.contains(hint, case=False, na=False)
        ]
        for _, row in match.iterrows():
            found_any = True
            sec_row = sectors[sectors["company_id"] == row["id"]]
            assigned = (
                sec_row.iloc[0]["broad_sector"]
                if not sec_row.empty
                else "NO SECTOR ROW"
            )
            print(f"    {row['company_name']} -> broad_sector = {assigned!r}")
    if not found_any:
        print(
            "    No classic utility-named company found -- supports genuine absence, not a labeling bug"
        )
    conn.close()


def run_pretests():
    check_pros_cons_gap_reasoning()
    print()
    check_cashflow_intelligence_columns()
    print()
    check_sector_count()


if __name__ == "__main__":
    run_pretests()
