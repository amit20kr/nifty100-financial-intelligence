import os
import re
import sqlite3
from collections import defaultdict

LOG_FILE = "output/ratio_edge_cases.log"
DB_PATH = "db/nifty100.db"

# Grouping threshold configuration
FORMULA_DISCREPANCY_SECTOR_THRESHOLD_PCT = (
    0.5  # If >50% of mismatches in sector have same sign
)


def run():
    print("Starting triage script...")

    if not os.path.exists(LOG_FILE):
        print(f"{LOG_FILE} not found.")
        return

    # 1. Parse existing logs & deduplicate (take the latest for each company/year/metric)
    parsed_entries = {}

    # Regex to match the newer Day 12 format (with fallback for variations)
    # 2026-07-22 23:37:15,122 - [ROE_MISMATCH] TRENT|2024-03|computed=31.56|source=27.20|diff=16.0% - category: to_be_triaged
    pattern = re.compile(
        r"^(.*?) - \[(.*?)\] ([^|]+)\|([^|]+)\|computed=([\d.-]+)\|source=([\d.-]+)\|diff=([\d.-]+)% .*?category: (.*)$"
    )

    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Skip SKIPPED lines if they already exist, we'll handle them via DB
            if "SKIPPED: missing_data" in line:
                continue

            match = pattern.match(line)
            if match:
                (
                    timestamp,
                    metric_type,
                    company,
                    year,
                    computed_str,
                    source_str,
                    diff_str,
                    category,
                ) = match.groups()
                key = (metric_type, company, year)
                parsed_entries[key] = {
                    "timestamp": timestamp,
                    "metric_type": metric_type,
                    "company": company,
                    "year": year,
                    "computed": float(computed_str),
                    "source": float(source_str),
                    "diff": float(diff_str),
                    "category": category.strip(),
                    "original_line": line,
                }

    # 2. Query DB for Sectors and Missing Data
    conn = sqlite3.connect(DB_PATH)

    company_to_sector = {}
    for row in conn.execute("SELECT company_id, broad_sector FROM sectors"):
        company_to_sector[row[0]] = row[1]

    # Find missing ROCE/ROE for Financials (to inject SKIPPED lines)
    missing_data_entries = []
    c = conn.execute(
        """
        SELECT f.company_id, f.year, s.broad_sector, f.return_on_capital_employed_pct, f.return_on_equity_pct
        FROM financial_ratios f
        JOIN sectors s ON f.company_id = s.company_id
        WHERE s.broad_sector = 'Financials'
    """
    )
    for row in c:
        company, year, sector, roce, roe = row
        if roce is None:
            missing_data_entries.append(("ROCE_MISMATCH", company, year))
        if roe is None:
            missing_data_entries.append(("ROE_MISMATCH", company, year))

    # 3. Categorization Logic
    # Group by sector and company to find patterns
    sector_diff_signs = defaultdict(list)
    company_mismatch_counts = defaultdict(int)

    for key, entry in parsed_entries.items():
        if entry["category"] not in ("to_be_triaged", "formula_discrepancy"):
            # Already finalized
            continue

        company = entry["company"]
        sector = company_to_sector.get(company, "Unknown")
        comp = entry["computed"]
        src = entry["source"]

        # Determine sign of diff using (computed - source)
        diff_sign = 1 if comp > src else -1

        sector_diff_signs[(entry["metric_type"], sector)].append(diff_sign)
        company_mismatch_counts[(entry["metric_type"], company)] += 1

    final_output_lines = []

    # Process parsed entries
    for key, entry in parsed_entries.items():
        cat = entry["category"]
        if cat not in ("to_be_triaged", "formula_discrepancy"):
            # Terminal category (data_source_issue, version_difference, etc.)
            final_output_lines.append(entry["original_line"])
            continue

        comp = entry["computed"]
        src = entry["source"]
        metric_type = entry["metric_type"]
        company = entry["company"]
        year = entry["year"]
        sector = company_to_sector.get(company, "Unknown")
        diff_sign = 1 if comp > src else -1

        # RULE 1: Data Source Issue (Unit mismatch ~100x)
        # computed/source or source/computed ~ 100 (+- 20%)
        ratio = 0
        if src != 0:
            ratio = comp / src
        elif comp != 0:
            ratio = src / comp

        if 80 <= ratio <= 120 or (comp != 0 and 80 <= (src / comp) <= 120):
            cat = "data_source_issue"
        else:
            # Check sector pattern vs company isolation
            sector_signs = sector_diff_signs[(metric_type, sector)]
            same_sign_count = sum(1 for s in sector_signs if s == diff_sign)
            sector_consistency = same_sign_count / max(1, len(sector_signs))

            comp_count = company_mismatch_counts[(metric_type, company)]

            # RULE: Version Difference vs Formula Discrepancy
            # If isolated to 1-2 years for this company, it's a version difference
            if comp_count <= 2:
                cat = "version_difference"
            # Else if it matches the sector-wide bias, it's a formula discrepancy
            elif sector_consistency > FORMULA_DISCREPANCY_SECTOR_THRESHOLD_PCT:
                cat = "formula_discrepancy"
            else:
                # Default fallback if it's many years but doesn't align with sector
                cat = "version_difference"

        # Reconstruct line
        timestamp = entry["timestamp"]
        diff_pct = entry["diff"]
        new_line = f"{timestamp} - [{metric_type}] {company}|{year}|computed={comp:.2f}|source={src:.2f}|diff={diff_pct:.1f}% - category: {cat}"
        final_output_lines.append(new_line)

    # Append SKIPPED lines
    # Format: 2026-07-22 23:37:15,122 - [ROCE_MISMATCH] HDFCBANK|2024-03 - category: SKIPPED: missing_data
    import datetime

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,000")
    for metric, company, year in missing_data_entries:
        final_output_lines.append(
            f"{now_str} - [{metric}] {company}|{year} - category: SKIPPED: missing_data"
        )

    # Sort lines
    final_output_lines.sort()

    # Rewrite log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        for line in final_output_lines:
            f.write(line + "\n")

    print(
        f"Triage complete. Rewrote {len(final_output_lines)} deduped/categorized entries to {LOG_FILE}."
    )
    conn.close()


if __name__ == "__main__":
    run()
