import sqlite3

import pandas as pd


def _latest_year_per_company(df: pd.DataFrame) -> pd.DataFrame:
    """Reuse Day 30/31 convention: exclude TTM, sort by calendar year via int(year[:4])."""
    df = df[df["year"] != "TTM"].copy()
    df["cal_year"] = df["year"].str[:4].astype(int)
    idx = df.groupby("company_id")["cal_year"].idxmax()
    return df.loc[idx]


def run_pretests():
    conn = sqlite3.connect("db/nifty100.db")

    # 1. capital_allocation.csv completeness (Sprint 2 artifact) — spec explicitly
    #    requires this check before Day 32 aggregation runs.
    try:
        cap_alloc = pd.read_csv("output/capital_allocation.csv")
        n_companies = cap_alloc["company_id"].nunique()
        print(f"[1] capital_allocation.csv distinct companies: {n_companies} / 92")
        if n_companies < 92:
            missing = set(range(1, 93)) - set(cap_alloc["company_id"].unique())
            print(f"    WARNING: missing company_ids (sample): {list(missing)[:10]}")
    except FileNotFoundError:
        print("[1] FAILED: output/capital_allocation.csv not found")

    # 2. cashflow_pattern_label coverage in financial_ratios for latest non-TTM year —
    #    confirm every company reconciles to a bucket (including an explicit NULL
    #    bucket) rather than silently vanishing from the 92 total.
    fr = pd.read_sql_query(
        "SELECT company_id, year, cashflow_pattern_label, return_on_equity_pct, pat_cagr_5yr "
        "FROM financial_ratios",
        conn,
    )
    latest = _latest_year_per_company(fr)
    n_latest = latest["company_id"].nunique()
    null_pattern = latest["cashflow_pattern_label"].isna().sum()
    print(f"[2] Companies with a resolvable latest year: {n_latest} / 92")
    print(
        f"    Companies with NULL cashflow_pattern_label at latest year: {null_pattern}"
    )
    if n_latest < 92:
        print(f"    WARNING: {92 - n_latest} companies have no non-TTM row at all")

    # 3. Distribution summary reconciliation — pattern counts (including NULL bucket)
    #    must sum to n_latest, and n_latest + missing-from-financial_ratios must equal 92.
    dist = latest["cashflow_pattern_label"].fillna("NO_DATA").value_counts()
    print("[3] Pattern distribution (latest year, NULL shown as NO_DATA):")
    for label, cnt in dist.items():
        print(f"    {label}: {cnt}")
    print(f"    Sum check: {dist.sum()} (expect {n_latest})")

    # 4. Median computation sanity check with a synthetic NaN — confirms pandas
    #    skips NaN silently rather than propagating it, matching intended behaviour.
    synthetic = pd.Series([12.0, 18.0, float("nan"), 24.0])
    med = synthetic.median()
    print(f"[4] Synthetic median with 1 NaN present: {med} (expect 18.0)")

    # 5. Year-contiguity spot check on known non-March-FYE companies (ABB, SIEMENS)
    #    to confirm int(year[:4]) ordering, not string sort, is used before computing
    #    "prior year" for pattern-change detection.
    for ticker in ("ABB", "SIEMENS"):
        row = pd.read_sql_query(
            "SELECT id FROM companies WHERE company_name LIKE ?",
            conn,
            params=(f"%{ticker}%",),
        )
        if row.empty:
            print(f"[5] {ticker}: not found in companies table, skipping")
            continue
        cid = row.iloc[0]["id"]
        sub = fr[(fr["company_id"] == cid) & (fr["year"] != "TTM")].copy()
        sub["cal_year"] = sub["year"].str[:4].astype(int)
        sub = sub.sort_values("cal_year")
        if len(sub) < 2:
            print(f"[5] {ticker}: fewer than 2 non-TTM years, skipping")
            continue
        latest_row = sub.iloc[-1]
        prior_row = sub.iloc[-2]
        gap = latest_row["cal_year"] - prior_row["cal_year"]
        print(
            f"[5] {ticker}: latest_year={latest_row['year']} prior_year={prior_row['year']} "
            f"gap={gap} (flag if gap != 1)"
        )

    # 6. Smoke test — confirm at least one genuine YoY pattern change exists somewhere
    #    in the dataset, so Day 32's change-detection path isn't exercising a vacuous
    #    (always-empty) branch untested.
    fr_sorted = fr[fr["year"] != "TTM"].copy()
    fr_sorted["cal_year"] = fr_sorted["year"].str[:4].astype(int)
    fr_sorted = fr_sorted.sort_values(["company_id", "cal_year"])
    fr_sorted["prev_pattern"] = fr_sorted.groupby("company_id")[
        "cashflow_pattern_label"
    ].shift(1)
    fr_sorted["prev_year"] = fr_sorted.groupby("company_id")["cal_year"].shift(1)
    fr_sorted["year_gap"] = fr_sorted["cal_year"] - fr_sorted["prev_year"]
    changed = fr_sorted[
        (fr_sorted["year_gap"] == 1)
        & fr_sorted["prev_pattern"].notna()
        & (fr_sorted["cashflow_pattern_label"] != fr_sorted["prev_pattern"])
    ]
    print(
        f"[6] Genuine (contiguous, non-null) YoY pattern changes found: {len(changed)}"
    )
    if len(changed) == 0:
        print(
            "    WARNING: pattern_changes.csv will be empty — confirm this is expected, not a bug"
        )
    else:
        sample = changed.iloc[0]
        print(
            f"    Sample: company_id={sample['company_id']} "
            f"{sample['prev_year']}:{sample['prev_pattern']} -> "
            f"{sample['cal_year']}:{sample['cashflow_pattern_label']}"
        )

    conn.close()


if __name__ == "__main__":
    run_pretests()
