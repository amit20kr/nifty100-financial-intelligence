"""
Migration 006: Create peer_percentiles table.

Sprint 3 - Day 18
Creates the peer_percentiles table to store computed percentile ranks.
Implements a safe composite primary key: (company_id, peer_group_name, metric, year)
to support diversified multi-group memberships.
Adds year_mismatch_flag for peer group modal year comparison tracking.
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
logger = logging.getLogger(__name__)

DB_PATH = Path("db/nifty100.db")


def migrate():
    if not DB_PATH.exists():
        logger.error(f"Database not found at {DB_PATH}")
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Create peer_percentiles table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS peer_percentiles (
                company_id TEXT,
                peer_group_name TEXT,
                metric TEXT,
                value REAL,
                percentile_rank REAL,
                year TEXT,
                year_mismatch_flag INTEGER,
                PRIMARY KEY (company_id, peer_group_name, metric, year),
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        """
        )

        # Track migration execution
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cursor.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version)
            VALUES ('006_peer_percentiles')
        """
        )

        conn.commit()
        logger.info("Migration 006 applied successfully: peer_percentiles created.")


if __name__ == "__main__":
    migrate()
