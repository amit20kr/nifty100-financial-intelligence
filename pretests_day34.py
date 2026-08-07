from pathlib import Path

import pandas as pd

MIN_YEARS_ENV_KEY = "TEARSHEET_MIN_YEARS"


def _load_env_min_years() -> int:
    env_path = Path(".env")
    if not env_path.exists():
        print("[0] FAIL: .env not found")
        return 3
    text = env_path.read_text()
    for line in text.splitlines():
        if line.strip().startswith(MIN_YEARS_ENV_KEY):
            val = line.split("=", 1)[1].strip()
            print(f"[0] {MIN_YEARS_ENV_KEY}={val} (confirmed present in .env)")
            return int(val)
    print(
        f"[0] FAIL: {MIN_YEARS_ENV_KEY} not found in .env — Day 34 must not hardcode it"
    )
    return 3


def run_pretests():
    import sqlite3

    min_years = _load_env_min_years()
    conn = sqlite3.connect("db/nifty100.db")

    companies = pd.read_sql_query("SELECT id, company_name FROM companies", conn)
    pl = pd.read_sql_query("SELECT company_id, year FROM profitandloss", conn)
    fr = pd.read_sql_query("SELECT company_id, year FROM financial_ratios", conn)
    sectors = pd.read_sql_query("SELECT company_id, broad_sector FROM sectors", conn)

    def non_ttm_years(df, cid):
        return df[(df["company_id"] == cid) & (df["year"] != "TTM")]["year"].nunique()

    # 1. Combined min-years gate: min(profitandloss_years, financial_ratios_years)
    #    per company — catches companies where the two tables' coverage diverges.
    rows = []
    for cid in companies["id"]:
        pl_years = non_ttm_years(pl, cid)
        fr_years = non_ttm_years(fr, cid)
        combined_min = min(pl_years, fr_years)
        rows.append(
            {
                "company_id": cid,
                "pl_years": pl_years,
                "fr_years": fr_years,
                "min": combined_min,
            }
        )
    coverage = pd.DataFrame(rows)
    will_skip = coverage[coverage["min"] < min_years]
    will_generate = coverage[coverage["min"] >= min_years]
    print(
        f"[1] Companies passing min-years gate ({min_years}): {len(will_generate)} / 92"
    )
    print(f"    Companies to be skipped: {len(will_skip)}")
    if not will_skip.empty:
        merged = will_skip.merge(companies, left_on="company_id", right_on="id")
        for _, r in merged.iterrows():
            print(
                f"    SKIP: {r['company_name']} (pl_years={r['pl_years']}, fr_years={r['fr_years']})"
            )

    # 2. Boundary case: confirm companies with exactly `min_years` years (e.g. JIOFIN)
    #    are correctly INCLUDED (>=), not excluded (>).
    boundary = coverage[coverage["min"] == min_years]
    if not boundary.empty:
        merged = boundary.merge(companies, left_on="company_id", right_on="id")
        print(
            f"[2] Boundary-case companies at exactly {min_years} years (must be INCLUDED):"
        )
        for _, r in merged.iterrows():
            print(f"    {r['company_name']} -> min_years={r['min']}")
    else:
        print(
            f"[2] No company sits exactly at the {min_years}-year boundary — boundary logic untested by data"
        )

    # 3. Sector label enumeration + filename safety check.
    distinct_sectors = sectors["broad_sector"].dropna().unique()
    print(f"[3] Distinct broad_sector values: {len(distinct_sectors)} (expect 11)")
    for s in sorted(distinct_sectors):
        safe = "".join(c if c.isalnum() else "_" for c in s).strip("_")
        flag = "  <-- needs sanitization" if safe != s.replace(" ", "_") else ""
        print(f"    {s!r} -> {safe}.pdf{flag}")

    # 4. Small-sector guard — sectors with n<5 companies (echoes SMALL_SECTOR flag
    #    already used in composite_score.py) must not divide-by-zero on median.
    sector_counts = sectors["broad_sector"].value_counts()
    small = sector_counts[sector_counts < 5]
    print(f"[4] Small sectors (n<5, need SMALL_SECTOR-style handling): {dict(small)}")

    # 5. Cross-artifact join-gap check for companies that WILL be generated —
    #    confirms every generating company has a row in each supplementary file
    #    before the full 92-company batch run, not discovered mid-batch.
    generating_ids = set(will_generate["company_id"])

    def check_coverage(path, id_col, label, loader=pd.read_csv):
        p = Path(path)
        if not p.exists():
            print(f"[5] FAIL: {path} not found")
            return
        df = loader(p)
        present = set(df[id_col].unique())
        missing = generating_ids - present
        print(
            f"[5] {label}: {len(missing)} generating companies missing a row"
            f"{' -> ' + str(list(missing)[:10]) if missing else ''}"
        )

    check_coverage(
        "output/composite_scores_all.csv", "company_id", "composite_scores_all.csv"
    )
    check_coverage(
        "output/pros_cons_generated.csv", "company_id", "pros_cons_generated.csv"
    )
    check_coverage(
        "output/cashflow_intelligence.xlsx",
        "company_id",
        "cashflow_intelligence.xlsx",
        loader=pd.read_excel,
    )

    conn.close()


def verify_pdf_sizes(tearsheet_dir: str = "reports/tearsheets", min_kb: int = 30):
    """Windows-safe replacement for `find -size -30k` — run AFTER batch generation."""
    d = Path(tearsheet_dir)
    if not d.exists():
        print(f"[POST] FAIL: {tearsheet_dir} does not exist")
        return
    pdfs = list(d.glob("*.pdf"))
    print(f"[POST] {len(pdfs)} PDFs found in {tearsheet_dir}")
    undersized = [p for p in pdfs if p.stat().st_size < min_kb * 1024]
    if undersized:
        print(
            f"[POST] FAIL: {len(undersized)} PDFs under {min_kb}KB (likely blank/broken):"
        )
        for p in undersized:
            print(f"    {p.name}: {p.stat().st_size} bytes")
    else:
        print(f"[POST] All PDFs >= {min_kb}KB")


if __name__ == "__main__":
    run_pretests()
    print(
        "\n--- Run verify_pdf_sizes() separately AFTER batch generation completes ---"
    )
