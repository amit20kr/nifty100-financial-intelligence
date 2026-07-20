import pandas as pd
from pathlib import Path


def get_raw_tickers(filepath, header, col_name):
    try:
        df = pd.read_excel(filepath, header=header, engine="openpyxl")
        df.columns = df.columns.astype(str).str.strip()
        if col_name in df.columns:
            return set(df[col_name].dropna().astype(str).str.strip().tolist())
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return set()


def main():
    base_path = Path("data")
    companies_raw = get_raw_tickers(base_path / "raw/companies.xlsx", 1, "id")
    companies_norm = {t.upper() for t in companies_raw}

    files = [
        ("raw/profitandloss.xlsx", 1, "company_id"),
        ("raw/balancesheet.xlsx", 1, "company_id"),
        ("raw/cashflow.xlsx", 1, "company_id"),
        ("raw/analysis.xlsx", 1, "company_id"),
        ("raw/documents.xlsx", 1, "company_id"),
        ("raw/prosandcons.xlsx", 1, "company_id"),
        ("supporting/sectors.xlsx", 0, "company_id"),
        ("supporting/stock_prices.xlsx", 0, "company_id"),
        ("supporting/market_cap.xlsx", 0, "company_id"),
        ("supporting/financial_ratios.xlsx", 0, "company_id"),
        ("supporting/peer_groups.xlsx", 0, "company_id"),
    ]

    results = []

    for rel_path, header, col in files:
        fpath = base_path / rel_path
        raw_tickers = get_raw_tickers(fpath, header, col)

        for raw_t in raw_tickers:
            norm_t = raw_t.upper()
            if norm_t not in companies_norm:
                results.append(
                    {"file": rel_path, "raw_ticker": raw_t, "normalized": norm_t}
                )

    df_results = pd.DataFrame(results)
    output_path = Path("output/orphan_analysis.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not df_results.empty:
        df_results.to_csv(output_path, index=False)
        print(f"Wrote orphan analysis to {output_path}")

        orphan_summary = df_results.groupby("normalized")["file"].apply(list).to_dict()
        for t, flist in orphan_summary.items():
            print(f"{t}: found as orphan in {len(flist)} files -> {flist}")
    else:
        print("No orphans found!")


if __name__ == "__main__":
    main()
