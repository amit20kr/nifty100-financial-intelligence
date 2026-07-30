"""
db/migrations/migrate_005_market_cap_year.py
--------------------------------------------
Migration 005 — Fix market_cap.year to canonical YYYY-MM format.

ROOT CAUSE:
  src/etl/loader.py DATASET_REGISTRY had has_year=False for market_cap, so
  normalize_year_series() was never called. market_cap.year remained as bare
  '2024', '2023', etc. while financial_ratios.year is 'YYYY-MM' (e.g. '2024-03').
  This made LEFT JOIN market_cap ON company_id AND year produce zero matches —
  silently NULLing all P/E, P/B, dividend_yield_pct, and market_cap_crore columns
  in the FilterEngine and any downstream query.

FIX (two-part):
  1. loader.py DATASET_REGISTRY: has_year set to True (committed separately in Day 16).
     Future `make load` runs will produce canonical years automatically.
  2. This migration (005): UPDATE existing DB rows using the same normalize_year()
     function from src/etl/normaliser.py — not a bespoke string-slice — so the
     canonical value is byte-identical to what the ETL pipeline would produce.
     This is a data-only UPDATE. No ALTER TABLE. No full reload. No re-run of
     populate_ratios.py (financial_ratios is untouched).

LOCKED DECISIONS:
  - bare '2024' → '2023-03' is what normalize_year() produces for a 4-digit year
    (FY convention: year 2024 = fiscal year ending March 2024 = '2024-03').
    This is consistent with how profitandloss, balancesheet, cashflow are stored.
  - Non-March fiscal year-end companies (e.g. SIEMENS, Dec year-end) will still
    have NULL valuation metrics post-fix because market_cap stores calendar-year
    granularity only — there is no '2024-09' or '2024-12' row in market_cap.
    This is an ACCEPTED DATA LIMITATION, not a recurrence of the join bug.
    Document in screener output: valuation columns are NULL for non-March FY companies.

IDEMPOTENCY:
  - Uses schema_migrations tracking table (same pattern as migrations 002–004).
  - Safe to run multiple times — second run is a no-op.

Author: Bluestock Data Analytics Team
Sprint: 3 — Day 16
"""

import sqlite3
import os
import sys
import logging

# Ensure project root is on path when run directly
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.etl.normaliser import normalize_year

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("migrate_005")

MIGRATION_VERSION = "005_fix_market_cap_year_format"


def get_db_path() -> str:
    return os.getenv("DB_PATH", "db/nifty100.db")


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """
    )
    conn.commit()


def is_migration_applied(conn: sqlite3.Connection, version: str) -> bool:
    cur = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
    return cur.fetchone() is not None


def run_migration(conn: sqlite3.Connection) -> None:
    """
    Normalise all market_cap.year values using normalize_year() from normaliser.py.

    '2024' → '2024-03', '2023' → '2023-03', etc. (bare 4-digit → YYYY-03 per
    normalize_year() Rule 3: Bare 4-digit year defaults to March fiscal year close).
    """
    rows = conn.execute("SELECT DISTINCT year FROM market_cap").fetchall()
    raw_years = [r[0] for r in rows]
    log.info(f"market_cap distinct year values before migration: {raw_years}")

    updated_total = 0
    for raw_year in raw_years:
        canonical = normalize_year(raw_year)
        if canonical in ("PARSE_ERROR", "MISSING"):
            log.warning(
                f"  SKIP: '{raw_year}' → normalize_year returned '{canonical}' — leaving unchanged"
            )
            continue
        if canonical == raw_year:
            log.info(f"  Already canonical: '{raw_year}' — no update needed")
            continue
        n = conn.execute(
            "UPDATE market_cap SET year = ? WHERE year = ?", (canonical, raw_year)
        ).rowcount
        log.info(f"  Updated: '{raw_year}' → '{canonical}' ({n} rows)")
        updated_total += n

    conn.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)", (MIGRATION_VERSION,)
    )
    conn.commit()
    log.info(f"Migration {MIGRATION_VERSION}: {updated_total} market_cap rows updated.")

    # Post-migration verification
    sample = conn.execute(
        "SELECT company_id, year, market_cap_crore FROM market_cap ORDER BY company_id LIMIT 5"
    ).fetchall()
    log.info("Post-migration sample:")
    for r in sample:
        log.info(f"  {r}")


def main() -> int:
    db_path = get_db_path()
    if not os.path.exists(db_path):
        log.error(f"Database not found at {db_path}. Run 'make load' first.")
        return 1

    conn = sqlite3.connect(db_path)
    try:
        ensure_migrations_table(conn)

        if is_migration_applied(conn, MIGRATION_VERSION):
            log.info(
                f"Migration {MIGRATION_VERSION} already applied — skipping (no-op)."
            )
            return 0

        log.info(f"Applying migration {MIGRATION_VERSION}...")
        run_migration(conn)
        log.info(f"Migration {MIGRATION_VERSION} complete.")
        return 0
    except Exception as e:
        log.error(f"Migration failed: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
