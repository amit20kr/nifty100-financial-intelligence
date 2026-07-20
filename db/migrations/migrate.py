"""
db/migrations/migrate.py
------------------------
Idempotent Python migration runner for nifty100.db.

Migration 002 — Add ratio columns to financial_ratios
------------------------------------------------------
Adds computed KPI columns that do not exist in the original schema.sql,
covering Days 08–11 of Sprint 2.

DESIGN DECISIONS (recorded here for auditability):
- return_on_capital_employed_pct, return_on_assets_pct: Day 08 formulas;
  persisted (not screener-only) so Sprint 3 screener can JOIN without
  live recomputation.
- net_debt_cr: Day 09 formula; persisted; NEGATIVE values are valid (net
  cash position) — no coercion applied anywhere in the pipeline.
- icr_at_risk_flag: NULL = debt-free company (not evaluated), 0 = not at
  risk, 1 = at risk. Do NOT default to 0 for NULL — these two states are
  semantically distinct.
- composite_quality_score: Sprint 2 interim proxy = CFO/PAT 5yr average
  (raw ratio, not 0-100 scale). Sprint 3 will introduce a true composite
  health score as a separate column/artifact.
- high_leverage_flag, icr_at_risk_flag stored as INTEGER (0/1/NULL) per
  SQLite convention. Day 12 insert layer must coerce Python bool via int().

IDEMPOTENCY:
- Uses schema_migrations tracking table to record applied versions.
- Checks PRAGMA table_info before each ALTER TABLE.
- Safe to run multiple times — second run exits 0 with no-op message.
"""

import sqlite3
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("migrate")

MIGRATION_VERSION = "002_add_ratio_columns"

# All columns to add: (column_name, sql_type)
COLUMNS_TO_ADD = [
    ("return_on_capital_employed_pct", "REAL"),
    ("return_on_assets_pct", "REAL"),
    ("net_debt_cr", "REAL"),
    ("revenue_cagr_5yr", "REAL"),
    ("pat_cagr_5yr", "REAL"),
    ("eps_cagr_5yr", "REAL"),
    ("composite_quality_score", "REAL"),
    ("icr_label", "TEXT"),
    ("icr_at_risk_flag", "INTEGER"),  # NULL=debt-free, 0=safe, 1=at risk
    ("high_leverage_flag", "INTEGER"),  # 0=False, 1=True; suppressed for Financials
    ("revenue_cagr_5yr_flag", "TEXT"),
    ("pat_cagr_5yr_flag", "TEXT"),
    ("eps_cagr_5yr_flag", "TEXT"),
]


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


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def run_migration(conn: sqlite3.Connection) -> None:
    existing = get_existing_columns(conn, "financial_ratios")
    added = []
    skipped = []

    for col_name, col_type in COLUMNS_TO_ADD:
        if col_name in existing:
            skipped.append(col_name)
        else:
            conn.execute(
                f"ALTER TABLE financial_ratios ADD COLUMN {col_name} {col_type}"
            )
            added.append(col_name)

    conn.execute(
        "INSERT INTO schema_migrations (version) VALUES (?)", (MIGRATION_VERSION,)
    )
    conn.commit()

    if added:
        log.info(f"Migration {MIGRATION_VERSION}: added columns: {added}")
    if skipped:
        log.info(
            f"Migration {MIGRATION_VERSION}: columns already existed (skipped): {skipped}"
        )


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
