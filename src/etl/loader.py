"""
loader.py
=========
Excel data loader for the Nifty 100 Financial Intelligence Platform.

Reads all 7 core + 5 supplementary datasets from disk, applies field-level
normalisation (ticker + year), deduplicates composite keys, and returns clean
DataFrames ready for SQLite insertion.

Also generates a per-table load_audit record for downstream QA.

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 2
Standard: PEP8 | type hints | one-line docstrings on every public function
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import sqlite3
import pandas as pd
from dotenv import load_dotenv
import os

from src.etl.normaliser import (
    normalize_ticker_series,
    normalize_year_series,
    SENTINEL_PARSE_ERROR,
    SENTINEL_MISSING,
)
from src.etl.validator import DataValidator

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
load_dotenv()
logger = logging.getLogger(__name__)

RAW_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw"))
SUPPORTING_DIR = Path(os.getenv("SUPPORTING_DATA_DIR", "data/supporting"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
DB_DIR = Path("db")
DB_PATH = DB_DIR / "nifty100.db"
SCHEMA_PATH = Path("src/etl/schema.sql")


# ---------------------------------------------------------------------------
# Dataset Registry
# ---------------------------------------------------------------------------
# Each entry defines:
#   filename   : the .xlsx file on disk
#   directory  : RAW_DIR or SUPPORTING_DIR
#   header_row : 1 for core datasets (metadata in row 0), 0 for supplementary
#   has_year   : whether the table has a 'year' column to normalise
#   sheet      : sheet name (None = first sheet)
DATASET_REGISTRY: list[dict] = [
    # ── Core datasets ─────────────────────────────────────────────────────
    {
        "table": "companies",
        "filename": "companies.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": False,
        "pk_cols": ["id"],
    },
    {
        "table": "profitandloss",
        "filename": "profitandloss.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": True,
        "pk_cols": ["company_id", "year"],
    },
    {
        "table": "balancesheet",
        "filename": "balancesheet.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": True,
        "pk_cols": ["company_id", "year"],
    },
    {
        "table": "cashflow",
        "filename": "cashflow.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": True,
        "pk_cols": ["company_id", "year"],
    },
    {
        "table": "analysis",
        "filename": "analysis.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": False,
        "pk_cols": ["company_id"],
    },
    {
        "table": "documents",
        "filename": "documents.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": True,
        "pk_cols": ["company_id", "year"],
    },
    {
        "table": "prosandcons",
        "filename": "prosandcons.xlsx",
        "directory": RAW_DIR,
        "header_row": 1,
        "has_year": False,
        "pk_cols": ["id"],
    },
    # ── Supplementary datasets ────────────────────────────────────────────
    {
        "table": "sectors",
        "filename": "sectors.xlsx",
        "directory": SUPPORTING_DIR,
        "header_row": 0,
        "has_year": False,
        "pk_cols": ["company_id"],
    },
    {
        "table": "stock_prices",
        "filename": "stock_prices.xlsx",
        "directory": SUPPORTING_DIR,
        "header_row": 0,
        "has_year": False,
        "pk_cols": ["company_id", "date"],
    },
    {
        "table": "market_cap",
        "filename": "market_cap.xlsx",
        "directory": SUPPORTING_DIR,
        "header_row": 0,
        "has_year": False,
        "pk_cols": ["company_id", "year"],
    },
    {
        "table": "financial_ratios",
        "filename": "financial_ratios.xlsx",
        "directory": SUPPORTING_DIR,
        "header_row": 0,
        "has_year": True,
        "pk_cols": ["company_id", "year"],
    },
    {
        "table": "peer_groups",
        "filename": "peer_groups.xlsx",
        "directory": SUPPORTING_DIR,
        "header_row": 0,
        "has_year": False,
        "pk_cols": ["id"],
    },
]


# ---------------------------------------------------------------------------
# LoadAuditRecord — structured log of one table's load statistics
# ---------------------------------------------------------------------------
@dataclass
class LoadAuditRecord:
    """Single row of load_audit.csv representing one table load."""

    table: str
    source_file: str
    rows_in: int = 0
    rows_out: int = 0
    rows_rejected: int = 0
    rejection_reasons: str = ""
    parse_errors: int = 0
    duplicates_removed: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    runtime_s: float = 0.0
    status: str = "OK"
    db_rows: int = 0
    db_fk_ok: bool = False


# ---------------------------------------------------------------------------
# DataLoader
# ---------------------------------------------------------------------------
class DataLoader:
    """Loads, normalises, and deduplicates all 12 Nifty 100 datasets.

    Usage::

        loader = DataLoader()
        dataframes = loader.load_all()
        audit_df   = loader.get_audit_log()
    """

    def __init__(self) -> None:
        """Initialise loader; validate that all source directories exist."""
        self._frames: dict[str, pd.DataFrame] = {}
        self._audit: list[LoadAuditRecord] = []

        for d in (RAW_DIR, SUPPORTING_DIR, OUTPUT_DIR):
            d.mkdir(parents=True, exist_ok=True)

        logger.info("DataLoader initialised. RAW=%s | SUPP=%s", RAW_DIR, SUPPORTING_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_all(self) -> dict[str, pd.DataFrame]:
        """Load, normalise, and deduplicate all 12 datasets.

        Returns:
            Dict mapping table name → clean DataFrame.
        """
        for cfg in DATASET_REGISTRY:
            self._load_one(cfg)

        # Run Schema Validation
        validator = DataValidator()
        self._frames = validator.validate(self._frames)

        return self._frames

    def get_frame(self, table: str) -> Optional[pd.DataFrame]:
        """Return the cleaned DataFrame for a specific table name."""
        return self._frames.get(table)

    def get_audit_log(self) -> pd.DataFrame:
        """Return the load audit log as a DataFrame."""
        return pd.DataFrame([asdict(r) for r in self._audit])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_one(self, cfg: dict) -> None:
        """Execute the full load → normalise → deduplicate pipeline for one table."""
        table = cfg["table"]
        fpath = cfg["directory"] / cfg["filename"]
        start = time.perf_counter()
        audit = LoadAuditRecord(table=table, source_file=str(fpath))

        logger.info("Loading [%s] from %s", table, fpath)

        # ── 1. Read from disk ──────────────────────────────────────────
        try:
            df = pd.read_excel(fpath, header=cfg["header_row"], engine="openpyxl")
        except FileNotFoundError:
            logger.error("File not found: %s", fpath)
            audit.status = "FILE_NOT_FOUND"
            self._audit.append(audit)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to read %s: %s", fpath, exc)
            audit.status = "READ_ERROR"
            self._audit.append(audit)
            return

        audit.rows_in = len(df)

        # ── 2. Strip column names ──────────────────────────────────────
        df.columns = df.columns.astype(str).str.strip()
        if table == "documents" and "Year" in df.columns:
            df.rename(columns={"Year": "year"}, inplace=True)

        # ── 2a. Reshape hook (Pivot sequence gap fix) ──────────────────
        if cfg.get("reshape") == "pivot":
            logger.info("[%s] Reshaping long-format data...", table)
            pivot_idx = cfg.get("pivot_index", "company_id")
            pivot_col = cfg.get("pivot_col")
            pivot_val = cfg.get("pivot_val")

            if pivot_col in df.columns and pivot_val in df.columns:
                # Capture all unique companies pre-pivot to avoid dropping partial data
                all_companies = pd.DataFrame({pivot_idx: df[pivot_idx].unique()})

                # Pivot with aggfunc='first' to handle missing/duplicate cells safely
                df_pivoted = df.pivot_table(
                    index=pivot_idx,
                    columns=pivot_col,
                    values=pivot_val,
                    aggfunc="first",
                ).reset_index()

                # Left-join against full set to retain all companies
                df = all_companies.merge(df_pivoted, on=pivot_idx, how="left")
            else:
                logger.warning("[%s] Pivot columns not found, skipping pivot.", table)

        # ── 3. Normalise company_id / ticker ──────────────────────────
        if "company_id" in df.columns:
            df["company_id"] = normalize_ticker_series(df["company_id"])
        elif "id" in df.columns and table == "companies":
            # companies.id IS the ticker
            df["id"] = normalize_ticker_series(df["id"])

        # ── 4. Normalise year label ────────────────────────────────────
        if cfg["has_year"] and "year" in df.columns:
            df["year"] = normalize_year_series(df["year"])
            parse_errors = (df["year"] == SENTINEL_PARSE_ERROR).sum()
            if parse_errors > 0:
                logger.warning(
                    "[%s] %d year PARSE_ERRORs detected", table, parse_errors
                )
                audit.parse_errors = int(parse_errors)

        # ── 5. Deduplicate on PK ───────────────────────────────────────
        if "pk_cols" in cfg:
            pk = cfg["pk_cols"]
            before_len = len(df)
            df.drop_duplicates(subset=pk, keep="first", inplace=True)
            dupes = before_len - len(df)
            audit.duplicates_removed = dupes
            if dupes > 0:
                logger.warning("[%s] Removed %d duplicate rows", table, dupes)
                # Diagnostic for Component 3 (balancesheet dupes)
                if dupes >= 90:  # ~ len(companies)
                    logger.warning(
                        "[%s] DIAGNOSTIC: Duplicates removed (%d) approaches/exceeds company count. Check source for full-row rollups.",
                        table,
                        dupes,
                    )

        # ── 6. Reject rows where critical IDs are MISSING/PARSE_ERROR ──
        rejection_mask = pd.Series(False, index=df.index)
        rejection_reasons: list[str] = []

        if "company_id" in df.columns:
            bad = df["company_id"].isin([SENTINEL_MISSING, SENTINEL_PARSE_ERROR])
            if bad.any():
                rejection_mask |= bad
                rejection_reasons.append(
                    f"company_id={SENTINEL_MISSING}/{SENTINEL_PARSE_ERROR}"
                )

        rows_rejected = int(rejection_mask.sum())
        df = df[~rejection_mask].copy()
        audit.rows_rejected = rows_rejected
        audit.rejection_reasons = "; ".join(rejection_reasons)
        audit.rows_out = len(df)

        # ── 7. Store ──────────────────────────────────────────────────
        self._frames[table] = df

        audit.runtime_s = round(time.perf_counter() - start, 4)
        audit.status = (
            "OK" if rows_rejected == 0 and audit.parse_errors == 0 else "WARNING"
        )

        logger.info(
            "[%s] in=%d out=%d rejected=%d dupes=%d parse_err=%d (%.3fs)",
            table,
            audit.rows_in,
            audit.rows_out,
            audit.rows_rejected,
            audit.duplicates_removed,
            audit.parse_errors,
            audit.runtime_s,
        )
        self._audit.append(audit)

    def _write_audit_log(self) -> None:
        """Persist the load audit log to output/load_audit.csv."""
        audit_df = self.get_audit_log()
        audit_path = OUTPUT_DIR / "load_audit.csv"
        audit_df.to_csv(audit_path, index=False)
        logger.info("Audit log written → %s", audit_path)

    def save_to_db(self) -> None:
        """Persist validated DataFrames to SQLite using strict schema and constraints."""
        DB_DIR.mkdir(parents=True, exist_ok=True)

        load_sequence = [
            "companies",
            "profitandloss",
            "balancesheet",
            "cashflow",
            "analysis",
            "documents",
            "prosandcons",
            "sectors",
            "market_cap",
            "stock_prices",
            "financial_ratios",
            "peer_groups",
        ]

        logger.info("Starting database persistence (12 tables)")
        with sqlite3.connect(DB_PATH) as conn:
            # 1. Execute schema with FK enforcement temporarily OFF
            conn.execute("PRAGMA foreign_keys = OFF;")
            with open(SCHEMA_PATH, "r") as f:
                conn.executescript(f.read())

            # 2. Re-enable FKs for strict inserts
            conn.execute("PRAGMA foreign_keys = ON;")

            # 3. Explicit Transaction for inserts
            class NoCommitConn:
                def __init__(self, connection):
                    self.conn = connection

                def cursor(self):
                    return self.conn.cursor()

                def execute(self, *args, **kwargs):
                    return self.conn.execute(*args, **kwargs)

                def executemany(self, *args, **kwargs):
                    return self.conn.executemany(*args, **kwargs)

                def commit(self):
                    pass

                def rollback(self):
                    pass

            try:
                conn.execute("BEGIN TRANSACTION;")
                wrapped_conn = NoCommitConn(conn)
                for table in load_sequence:
                    if table not in self._frames or self._frames[table] is None:
                        logger.warning(
                            "Table %s not found in processed frames, skipping DB insert.",
                            table,
                        )
                        continue

                    df = self._frames[table]
                    # Insert, appending to the pre-created schema
                    df.to_sql(table, wrapped_conn, if_exists="append", index=False)
                    logger.info("Inserted %d rows into %s", len(df), table)

                conn.execute("COMMIT;")
                logger.info("Database persistence completed successfully.")

                # ── 4. DB Reconciliation Pass (Component 4) ────────────────────
                logger.info("Starting post-load reconciliation...")

                # FK Check
                fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
                fk_ok = len(fk_violations) == 0
                if not fk_ok:
                    logger.error("Foreign key violations found! %s", fk_violations)
                    # Raising to halt process since constraints failed
                    raise sqlite3.IntegrityError(
                        f"FK violations found: {fk_violations}"
                    )

                # Row counts cross-check
                for audit_rec in self._audit:
                    table = audit_rec.table
                    if table in self._frames and self._frames[table] is not None:
                        db_count = conn.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        df_count = len(self._frames[table])

                        audit_rec.db_rows = db_count
                        audit_rec.db_fk_ok = fk_ok

                        if db_count != df_count:
                            logger.error(
                                "[%s] RECONCILIATION FAILED: DB rows (%d) != DF rows (%d)",
                                table,
                                db_count,
                                df_count,
                            )
                            audit_rec.status = "ROW_MISMATCH"
                        else:
                            if audit_rec.status == "OK":
                                audit_rec.status = "LOADED_OK"

                # Write second-pass audit
                self._write_audit_log()

            except Exception as e:
                conn.execute("ROLLBACK;")
                logger.error(
                    "Transaction failed during table load. Rolled back. Error: %s", e
                )
                raise


# ---------------------------------------------------------------------------
# CLI entry-point (python -m src.etl.loader)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    loader = DataLoader()
    frames = loader.load_all()
    loader.save_to_db()

    print("\n=== LOAD SUMMARY ===")
    for name, df in frames.items():
        print(f"  {name:20s}  ->  {len(df):>5} rows  |  {df.shape[1]} cols")
    print(f"\nAudit log -> {OUTPUT_DIR / 'load_audit.csv'}")
    print(f"Database  -> {DB_PATH}")
