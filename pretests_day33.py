import sqlite3
from pathlib import Path

import pandas as pd

TEST_COMPANIES = ["TCS", "HDFCBANK", "RELIANCE", "SUNPHARMA", "TATASTEEL"]
MIN_YEARS = 3  # matches TEARSHEET_MIN_YEARS


def _latest_year_row(df: pd.DataFrame) -> pd.Series | None:
    non_ttm = df[df["year"] != "TTM"].copy()
    if non_ttm.empty:
        return None
    non_ttm["cal_year"] = non_ttm["year"].str[:4].astype(int)
    return non_ttm.sort_values("cal_year").iloc[-1]


def run_pretests():
    conn = sqlite3.connect("db/nifty100.db")

    companies = pd.read_sql_query(
        "SELECT id, company_name, nse_profile FROM companies", conn
    )

    # 1. BLOCKING: master composite score export must exist and cover all 92
    #    companies. screener_output.xlsx only covers preset-passers, and the
    #    DB's composite_quality_score is the unrelated CFO/PAT metric — neither
    #    is a valid source for a 0-100 header badge.
    score_path = Path("output/composite_scores_all.csv")
    if not score_path.exists():
        print("[1] BLOCKING FAIL: output/composite_scores_all.csv does not exist yet.")
        print("    screener_output.xlsx only covers preset-passers (not all 92).")
        print("    DB's composite_quality_score is the CFO/PAT metric, NOT 0-100.")
        print("    Generate the full-universe export before building the header.")
    else:
        scores = pd.read_csv(score_path)
        n = scores["company_id"].nunique()
        null_scores = scores["screener_composite_score"].isna().sum()
        print(
            f"[1] composite_scores_all.csv: {n} / 92 companies, {null_scores} null scores"
        )
        rng = (
            scores["screener_composite_score"].min(),
            scores["screener_composite_score"].max(),
        )
        print(
            f"    Score range observed: {rng} (expect within [0, 100], NOT [-14, 15])"
        )

    # 2. Ticker field does not exist as a column — inspect nse_profile format
    #    for the 5 test companies before wiring any extraction regex.
    print(
        "[2] nse_profile raw values for test companies (inspect before extracting ticker):"
    )
    for name in TEST_COMPANIES:
        row = companies[
            companies["company_name"].str.contains(name, case=False, na=False)
        ]
        if row.empty:
            print(f"    {name}: NOT FOUND in companies table")
            continue
        print(f"    {name}: nse_profile={row.iloc[0]['nse_profile']!r}")

    # 3. market_cap_crore non-null at latest year for test companies — regression
    #    guard against the historical Sprint 1 market_cap year-format bug.
    mc = pd.read_sql_query(
        "SELECT company_id, year, market_cap_crore FROM market_cap", conn
    )
    print("[3] Latest-year market_cap_crore for test companies:")
    for name in TEST_COMPANIES:
        crow = companies[
            companies["company_name"].str.contains(name, case=False, na=False)
        ]
        if crow.empty:
            continue
        cid = crow.iloc[0]["id"]
        sub = mc[mc["company_id"] == cid]
        latest = _latest_year_row(sub)
        if latest is None or pd.isna(latest.get("market_cap_crore")):
            print(f"    {name}: FAIL — no market_cap_crore at latest year")
        else:
            print(f"    {name}: {latest['year']} -> {latest['market_cap_crore']} Cr")

    # 4. pros_cons_generated.csv coverage + confidence-ranked top-6 cap check
    pc_path = Path("output/pros_cons_generated.csv")
    if not pc_path.exists():
        print("[4] FAIL: output/pros_cons_generated.csv not found")
    else:
        pc = pd.read_csv(pc_path)
        print("[4] Pros/Cons coverage for test companies (capped top-6 by confidence):")
        for name in TEST_COMPANIES:
            crow = companies[
                companies["company_name"].str.contains(name, case=False, na=False)
            ]
            if crow.empty:
                continue
            cid = crow.iloc[0]["id"]
            sub = pc[pc["company_id"] == cid]
            pros = sub[sub["type"] == "pro"].sort_values(
                "confidence_pct", ascending=False
            )
            cons = sub[sub["type"] == "con"].sort_values(
                "confidence_pct", ascending=False
            )
            print(
                f"    {name}: {len(pros)} pros (showing top {min(6, len(pros))}), "
                f"{len(cons)} cons (showing top {min(6, len(cons))})"
            )

        # Identify the single highest-signal company across all 92 to stress-test
        # page-overflow risk beyond the 5 named blue-chips.
        counts = pc.groupby("company_id").size().sort_values(ascending=False)
        if not counts.empty:
            top_cid = counts.index[0]
            top_name = companies.loc[companies["id"] == top_cid, "company_name"]
            top_name = top_name.iloc[0] if not top_name.empty else top_cid
            print(
                f"    Highest total pro+con count in dataset: {top_name} "
                f"({counts.iloc[0]} rules triggered) — visually test this one too, "
                f"not just the 5 named companies"
            )

    # 5. cashflow_intelligence.xlsx coverage for test companies
    cf_path = Path("output/cashflow_intelligence.xlsx")
    if not cf_path.exists():
        print("[5] FAIL: output/cashflow_intelligence.xlsx not found")
    else:
        cf = pd.read_excel(cf_path)
        print("[5] cashflow_intelligence.xlsx coverage for test companies:")
        for name in TEST_COMPANIES:
            crow = companies[
                companies["company_name"].str.contains(name, case=False, na=False)
            ]
            if crow.empty:
                continue
            cid = crow.iloc[0]["id"]
            sub = cf[cf["company_id"] == cid]
            if sub.empty:
                print(f"    {name}: FAIL — no row in cashflow_intelligence.xlsx")
            else:
                label = sub.iloc[0].get("capital_allocation_label", "MISSING")
                print(f"    {name}: capital_allocation_label={label}")

    # 6. Minimum-year-history guard for chart rendering
    pl = pd.read_sql_query("SELECT company_id, year FROM profitandloss", conn)
    print(f"[6] Year-history check (MIN_YEARS={MIN_YEARS}) for test companies:")
    for name in TEST_COMPANIES:
        crow = companies[
            companies["company_name"].str.contains(name, case=False, na=False)
        ]
        if crow.empty:
            continue
        cid = crow.iloc[0]["id"]
        n_years = pl[(pl["company_id"] == cid) & (pl["year"] != "TTM")][
            "year"
        ].nunique()
        status = "OK" if n_years >= MIN_YEARS else "FAIL — below minimum"
        print(f"    {name}: {n_years} non-TTM years ({status})")

    conn.close()


if __name__ == "__main__":
    run_pretests()
