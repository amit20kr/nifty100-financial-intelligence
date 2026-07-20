"""
validator.py
============
Schema & Data Quality Validator for the Nifty 100 ETL pipeline.
Enforces 16 Data Quality rules (DQ-01 to DQ-16).

Author  : Bluestock Data Analytics Team
Sprint  : 1 — Day 3
Standard: PEP8 | type hints | declarative registry pattern
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.etl.normaliser import (
    SENTINEL_MISSING,
    SENTINEL_PARSE_ERROR,
    SENTINEL_TTM,
    SENTINEL_PARTIAL,
)

load_dotenv()
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BS_TOLERANCE = float(os.getenv("BS_BALANCE_TOLERANCE_PCT", "1.0")) / 100.0
OPM_TOLERANCE = float(os.getenv("OPM_CROSS_CHECK_TOLERANCE_PCT", "1.0"))
CF_TOLERANCE = float(os.getenv("DQ_CASHFLOW_MISMATCH_TOLERANCE_CR", "10.0"))

# Sentinels that should be excluded from numeric math
NUMERIC_SENTINELS = {
    SENTINEL_TTM,
    SENTINEL_PARTIAL,
    SENTINEL_PARSE_ERROR,
    SENTINEL_MISSING,
}


@dataclass
class ValidationFailure:
    """Represents a single data quality violation."""

    rule_id: str
    table: str
    company_id: str
    year: str
    field: str
    issue: str
    severity: str


class DataValidator:
    """Enforces 16 DQ rules on the raw DataFrames using a declarative registry."""

    def __init__(self) -> None:
        self.failures: list[ValidationFailure] = []
        self._coverage_drops: dict[str, int] = {}

        # Rule Registry: rule_id -> (function, severity, target_table(s))
        self.RULE_REGISTRY: dict[str, dict] = {
            "DQ-01": {
                "func": self._check_dq01,
                "severity": "CRITICAL",
                "table": "companies",
            },
            "DQ-02": {"func": self._check_dq02, "severity": "CRITICAL", "table": "ALL"},
            "DQ-03": {"func": self._check_dq03, "severity": "CRITICAL", "table": "ALL"},
            "DQ-04": {
                "func": self._check_dq04,
                "severity": "WARNING",
                "table": "balancesheet",
            },
            "DQ-05": {
                "func": self._check_dq05,
                "severity": "WARNING",
                "table": "profitandloss",
            },
            "DQ-06": {
                "func": self._check_dq06,
                "severity": "WARNING",
                "table": "profitandloss",
            },
            "DQ-07": {"func": self._check_dq07, "severity": "CRITICAL", "table": "ALL"},
            "DQ-08": {"func": self._check_dq08, "severity": "CRITICAL", "table": "ALL"},
            "DQ-09": {
                "func": self._check_dq09,
                "severity": "WARNING",
                "table": "cashflow",
            },
            "DQ-10": {
                "func": self._check_dq10,
                "severity": "WARNING",
                "table": "balancesheet",
            },
            "DQ-11": {
                "func": self._check_dq11,
                "severity": "WARNING",
                "table": "profitandloss",
            },
            "DQ-12": {
                "func": self._check_dq12,
                "severity": "WARNING",
                "table": "profitandloss",
            },
            "DQ-13": {
                "func": self._check_dq13,
                "severity": "WARNING",
                "table": "companies",
            },
            "DQ-14": {
                "func": self._check_dq14,
                "severity": "WARNING",
                "table": "profitandloss",
            },
            "DQ-15": {
                "func": self._check_dq15,
                "severity": "INFO",
                "table": "balancesheet",
            },
            "DQ-16": {
                "func": self._check_dq16,
                "severity": "WARNING",
                "table": "profitandloss",
            },
        }

    def validate(self, frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Run all registered DQ rules on the provided DataFrames.

        Args:
            frames: Dictionary of loaded DataFrames from DataLoader.
        Returns:
            Dictionary of validated and coerced DataFrames.
        """
        logger.info("Starting Schema Validation (15 DQ Rules)...")
        self.frames = frames

        # Run DQ-01 first, as it's a hard halt condition
        self._check_dq01()

        # Run remaining rules
        for rule_id, rule_config in self.RULE_REGISTRY.items():
            if rule_id == "DQ-01":
                continue  # already ran

            target = rule_config["table"]
            func = rule_config["func"]

            try:
                if target == "ALL":
                    func()
                elif target in self.frames and self.frames[target] is not None:
                    func(self.frames[target])
            except Exception as e:
                logger.error("Error executing %s: %s", rule_id, e)

        self._write_failures()
        self._emit_coverage_summary()
        return self.frames

    def _log_failure(
        self,
        rule_id: str,
        table: str,
        company_id: str,
        year: str,
        field: str,
        issue: str,
        severity: str,
    ) -> None:
        self.failures.append(
            ValidationFailure(rule_id, table, company_id, year, field, issue, severity)
        )

    def _write_failures(self) -> None:
        out_path = OUTPUT_DIR / "validation_failures.csv"
        if not self.failures:
            # Write empty file with headers
            pd.DataFrame(
                columns=[
                    f.name for f in ValidationFailure.__dataclass_fields__.values()
                ]
            ).to_csv(out_path, index=False)
            logger.info("Validation complete. Zero failures logged.")
            return

        df = pd.DataFrame([asdict(f) for f in self.failures])
        df.to_csv(out_path, index=False)
        criticals = (df["severity"] == "CRITICAL").sum()
        warnings = (df["severity"] == "WARNING").sum()
        logger.info(
            "Validation complete. Logged %d CRITICAL and %d WARNING issues to %s",
            criticals,
            warnings,
            out_path,
        )

    def _emit_coverage_summary(self) -> None:
        """Emit summary of dropped orphans to ensure we don't silently lose coverage."""
        if not self._coverage_drops:
            return
        logger.warning("--- ORPHAN DROP COVERAGE SUMMARY ---")
        for cid, count in self._coverage_drops.items():
            logger.warning("Dropped %d orphan rows for unknown ticker: %s", count, cid)

    # -----------------------------------------------------------------------
    # Rule Implementations
    # -----------------------------------------------------------------------

    def _check_dq01(self) -> None:
        """DQ-01: Company PK Uniqueness. Halt if duplicate ticker."""
        if "companies" not in self.frames:
            return
        df = self.frames["companies"]
        ticker_col = "id" if "id" in df.columns else "company_id"

        dupes = df[df.duplicated(subset=[ticker_col], keep=False)]
        if not dupes.empty:
            logger.critical(
                "DQ-01: CRITICAL FAILURE. Duplicate tickers found in master list: %s",
                dupes[ticker_col].unique(),
            )
            for _, row in dupes.iterrows():
                self._log_failure(
                    "DQ-01",
                    "companies",
                    str(row[ticker_col]),
                    "N/A",
                    ticker_col,
                    "Duplicate company PK",
                    "CRITICAL",
                )
            self._write_failures()
            sys.exit(2)  # Hard halt for CI/CD

    def _check_dq02(self) -> None:
        """DQ-02: Composite PK Uniqueness. Halt or reject if duplicate (company_id, year)."""
        for table, df in self.frames.items():
            if "company_id" not in df.columns or "year" not in df.columns:
                continue

            # Find duplicates
            dupes = df[df.duplicated(subset=["company_id", "year"], keep=False)]
            if not dupes.empty:
                logger.critical(
                    "DQ-02: CRITICAL FAILURE. Duplicate (company_id, year) in %s", table
                )
                for _, row in dupes.iterrows():
                    self._log_failure(
                        "DQ-02",
                        table,
                        str(row.get("company_id")),
                        str(row.get("year")),
                        "(company_id, year)",
                        "Duplicate composite PK",
                        "CRITICAL",
                    )
                self._write_failures()
                sys.exit(2)  # Hard halt

    def _check_dq03(self) -> None:
        """DQ-03: FK Integrity. Reject orphan rows in all time-series tables."""
        if "companies" not in self.frames:
            return
        master_df = self.frames["companies"]
        ticker_col = "id" if "id" in master_df.columns else "company_id"
        valid_companies = set(master_df[ticker_col].dropna().unique())

        for table, df in self.frames.items():
            if table == "companies" or "company_id" not in df.columns:
                continue

            orphans = ~df["company_id"].isin(valid_companies)
            if orphans.any():
                orphan_counts = df.loc[orphans, "company_id"].value_counts()
                for cid, count in orphan_counts.items():
                    self._coverage_drops[str(cid)] = (
                        self._coverage_drops.get(str(cid), 0) + count
                    )
                    self._log_failure(
                        "DQ-03",
                        table,
                        str(cid),
                        "N/A",
                        "company_id",
                        "Orphan FK",
                        "CRITICAL",
                    )

                # Reject orphan rows
                self.frames[table] = df[~orphans].copy()

    def _check_dq04(self, df: pd.DataFrame) -> None:
        """DQ-04: Balance Sheet Balance."""
        if not {"total_assets", "total_liabilities"}.issubset(df.columns):
            return

        # Mask out NaNs
        mask = df["total_assets"].notna() & df["total_liabilities"].notna()
        # Avoid division by zero
        mask &= df["total_assets"] != 0

        diff_pct = (
            df.loc[mask, "total_assets"] - df.loc[mask, "total_liabilities"]
        ).abs() / df.loc[mask, "total_assets"]
        violators = df.loc[mask][diff_pct > BS_TOLERANCE]

        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-04",
                "balancesheet",
                str(row.get("company_id")),
                str(row.get("year")),
                "total_assets/liabilities",
                f"Imbalance > {BS_TOLERANCE*100}%",
                "WARNING",
            )

    def _check_dq05(self, df: pd.DataFrame) -> None:
        """DQ-05: OPM Cross-Check."""
        cols = {"opm_percentage", "operating_profit", "sales"}
        if not cols.issubset(df.columns):
            return

        # Component 5: BFSI Exemption for OPM Cross-check
        bfsi_companies = set()
        if "sectors" in self.frames and self.frames["sectors"] is not None:
            sectors_df = self.frames["sectors"]
            if (
                "broad_sector" in sectors_df.columns
                and "company_id" in sectors_df.columns
            ):
                bfsi_mask = sectors_df["broad_sector"] == "Financials"
                bfsi_companies = set(sectors_df.loc[bfsi_mask, "company_id"])

        mask = df[list(cols)].notna().all(axis=1) & (df["sales"] != 0)
        if bfsi_companies:
            mask &= ~df["company_id"].isin(bfsi_companies)

        computed_opm = (
            df.loc[mask, "operating_profit"] / df.loc[mask, "sales"]
        ) * 100.0
        diff = (df.loc[mask, "opm_percentage"] - computed_opm).abs()

        violators = df.loc[mask][diff > OPM_TOLERANCE]
        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-05",
                "profitandloss",
                str(row.get("company_id")),
                str(row.get("year")),
                "opm_percentage",
                f"Differs from computed by > {OPM_TOLERANCE}%",
                "WARNING",
            )

    def _check_dq06(self, df: pd.DataFrame) -> None:
        """DQ-06: Positive Sales."""
        if "sales" not in df.columns:
            return

        # In reality we should exclude banks. We'll flag all for now, analytics engine filters banks later.
        mask = df["sales"].notna() & (df["sales"] <= 0)
        violators = df[mask]
        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-06",
                "profitandloss",
                str(row.get("company_id")),
                str(row.get("year")),
                "sales",
                f"Sales <= 0 ({row['sales']})",
                "WARNING",
            )

    def _check_dq07(self) -> None:
        """DQ-07: Year Format."""
        for table, df in self.frames.items():
            if "year" not in df.columns:
                continue

            bad = df["year"] == SENTINEL_PARSE_ERROR
            if bad.any():
                violators = df[bad]
                for _, row in violators.iterrows():
                    self._log_failure(
                        "DQ-07",
                        table,
                        str(row.get("company_id")),
                        str(row.get("year")),
                        "year",
                        "Unparseable year format",
                        "CRITICAL",
                    )
                # Reject rows
                self.frames[table] = df[~bad].copy()

    def _check_dq08(self) -> None:
        """DQ-08: Ticker Format."""
        for table, df in self.frames.items():
            ticker_col = (
                "id" if table == "companies" and "id" in df.columns else "company_id"
            )
            if ticker_col not in df.columns:
                continue

            bad = df[ticker_col] == SENTINEL_MISSING
            # Check length 2-12 for valid ones
            lengths = df.loc[~bad, ticker_col].astype(str).str.len()
            out_of_range = (lengths < 2) | (lengths > 12)

            total_bad = bad | out_of_range.reindex(df.index, fill_value=False)

            if total_bad.any():
                violators = df[total_bad]
                for _, row in violators.iterrows():
                    self._log_failure(
                        "DQ-08",
                        table,
                        str(row[ticker_col]),
                        str(row.get("year", "N/A")),
                        ticker_col,
                        "Invalid or missing ticker format",
                        "CRITICAL",
                    )
                # Reject rows
                self.frames[table] = df[~total_bad].copy()

    def _check_dq09(self, df: pd.DataFrame) -> None:
        """DQ-09: Net Cash Check."""
        cols = {
            "net_cash_flow",
            "operating_activity",
            "investing_activity",
            "financing_activity",
        }
        if not cols.issubset(df.columns):
            return

        mask = df[list(cols)].notna().all(axis=1)
        computed = (
            df.loc[mask, "operating_activity"]
            + df.loc[mask, "investing_activity"]
            + df.loc[mask, "financing_activity"]
        )
        diff = (df.loc[mask, "net_cash_flow"] - computed).abs()

        violators = df.loc[mask][diff > CF_TOLERANCE]
        for idx, row in violators.iterrows():
            self._log_failure(
                "DQ-09",
                "cashflow",
                str(row.get("company_id")),
                str(row.get("year")),
                "net_cash_flow",
                f"Mismatch > {CF_TOLERANCE} Cr",
                "WARNING",
            )
            # Coerce net_cash_flow to computed
            self.frames["cashflow"].at[idx, "net_cash_flow"] = computed[idx]

    def _check_dq10(self, df: pd.DataFrame) -> None:
        """DQ-10: Non-Negative Fixed Assets."""
        if "fixed_assets" not in df.columns:
            return

        mask = df["fixed_assets"].notna() & (df["fixed_assets"] < 0)
        violators = df[mask]
        for idx, row in violators.iterrows():
            self._log_failure(
                "DQ-10",
                "balancesheet",
                str(row.get("company_id")),
                str(row.get("year")),
                "fixed_assets",
                f"Negative assets ({row['fixed_assets']})",
                "WARNING",
            )
            # Coerce
            self.frames["balancesheet"].at[idx, "fixed_assets"] = 0.0

    def _check_dq11(self, df: pd.DataFrame) -> None:
        """DQ-11: Tax Rate Range."""
        if "tax_percentage" not in df.columns:
            return

        mask = df["tax_percentage"].notna() & (
            (df["tax_percentage"] < 0) | (df["tax_percentage"] > 60)
        )
        violators = df[mask]
        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-11",
                "profitandloss",
                str(row.get("company_id")),
                str(row.get("year")),
                "tax_percentage",
                f"Out of range: {row['tax_percentage']}%",
                "WARNING",
            )

    def _check_dq12(self, df: pd.DataFrame) -> None:
        """DQ-12: Dividend Payout Cap."""
        if "dividend_payout" not in df.columns:
            return

        mask = df["dividend_payout"].notna() & (df["dividend_payout"] > 200)
        violators = df[mask]
        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-12",
                "profitandloss",
                str(row.get("company_id")),
                str(row.get("year")),
                "dividend_payout",
                f">200%: {row['dividend_payout']}%",
                "WARNING",
            )

    def _check_dq13(self, df: pd.DataFrame) -> None:
        """DQ-13: URL Format Check."""
        if "website" not in df.columns:
            return

        mask = df["website"].notna() & (df["website"].str.strip() != "")
        invalid = df[mask][
            ~df.loc[mask, "website"].str.match(r"^https?://", case=False, na=False)
        ]
        for _, row in invalid.iterrows():
            ticker_col = "id" if "id" in df.columns else "company_id"
            self._log_failure(
                "DQ-13",
                "companies",
                str(row.get(ticker_col)),
                "N/A",
                "website",
                f"Invalid URL format: {row['website']}",
                "WARNING",
            )

    def _check_dq14(self, df: pd.DataFrame) -> None:
        """DQ-14: EPS Sign Consistency."""
        if not {"eps", "net_profit"}.issubset(df.columns):
            return

        mask = (
            df["eps"].notna()
            & df["net_profit"].notna()
            & (df["net_profit"] > 0)
            & (df["eps"] <= 0)
        )
        violators = df[mask]
        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-14",
                "profitandloss",
                str(row.get("company_id")),
                str(row.get("year")),
                "eps",
                "EPS <= 0 but Net Profit > 0",
                "WARNING",
            )

    def _check_dq15(self, df: pd.DataFrame) -> None:
        """DQ-15: BSE/ASE Balance (ext.)"""
        if not {"total_assets", "total_liabilities"}.issubset(df.columns):
            return

        mask = df["total_assets"].notna() & df["total_liabilities"].notna()
        # Exact match
        strict_match = df.loc[mask, "total_assets"] == df.loc[mask, "total_liabilities"]
        violators = df.loc[mask][~strict_match]

        for _, row in violators.iterrows():
            self._log_failure(
                "DQ-15",
                "balancesheet",
                str(row.get("company_id")),
                str(row.get("year")),
                "total_assets/liabilities",
                "Strict balance mismatch",
                "INFO",
            )

    def _check_dq16(self, df: pd.DataFrame) -> None:
        """DQ-16: Coverage Check."""
        if "company_id" not in df.columns or "year" not in df.columns:
            return

        # Exclude sentinel years
        valid = df[~df["year"].isin(NUMERIC_SENTINELS)]
        counts = valid.groupby("company_id").size()
        under_5 = counts[counts < 5]

        for cid, count in under_5.items():
            self._log_failure(
                "DQ-16",
                "profitandloss",
                str(cid),
                "N/A",
                "year",
                f"Coverage < 5yr ({count} yrs)",
                "WARNING",
            )
