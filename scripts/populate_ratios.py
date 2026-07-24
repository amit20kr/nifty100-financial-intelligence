"""
scripts/populate_ratios.py
--------------------------
Day 12: Full ratio engine population for all companies × all years.

Architecture (per Claude Day 12 critical-bug review):
  Bug #1 fix — UNION driver: distinct (company_id, year) from profitandloss + balancesheet + cashflow
               UPSERT (INSERT ... ON CONFLICT DO UPDATE) — not a bare UPDATE
  Bug #2 fix — Per-row trailing 5yr CAGR for EVERY row, not one scalar per company
  Bug #3 fix — capex_intensity_pct + fcf_conversion_pct persisted alongside labels
  Bug #4 fix — earnings_per_share, book_value_per_share, dividend_payout_ratio_pct, total_debt_cr
               populated as direct copies from profitandloss / companies / balancesheet

Design decisions (locked):
  - UPDATE-column binding: dict-based named parameters (:col) — never positional tuples
  - CFO quality score: trailing 5yr rolling window PER ROW (min 3 of 5 valid), same window
    logic as CAGR
  - CAGR: trailing 5yr from each row's year as anchor — same for all rows, not per-company scalar
  - Idempotency: ON CONFLICT(company_id, year) DO UPDATE SET — second run produces identical results
  - All cross-checks (ROCE, ROE, capex) logged to output/ratio_edge_cases.log with category tag
  - capital_allocation.csv emitted at end with 8 spec-defined pattern labels

Canonical schema source: src/etl/schema.sql (see comment in db/migrations/migrate.py)
"""

import csv
import logging
import math
import os
import sqlite3
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path when run directly
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analytics.cagr import calculate_cagr
from src.analytics.cashflow_kpis import (
    CapexIntensityResult,
    CfoQualityResult,
    FcfConversionResult,
    FcfResult,
    capex_intensity,
    cfo_quality_score,
    classify_cashflow_pattern,
    fcf_conversion,
    free_cash_flow,
    verify_capex_cross_check,
)
from src.analytics.constants import CagrFlag
from src.analytics.ratios import (
    asset_turnover,
    debt_to_equity,
    interest_coverage_ratio,
    net_debt,
    net_profit_margin,
    operating_profit_margin,
    return_on_assets,
    return_on_capital_employed,
    return_on_equity,
)
from src.etl.normaliser import SENTINEL_TTM

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
ROCE_CROSS_CHECK_TOLERANCE_PCT: float = float(
    os.getenv("ROCE_CROSS_CHECK_TOLERANCE_PCT", "5.0")
)
ROE_CROSS_CHECK_TOLERANCE_PCT: float = float(
    os.getenv("ROE_CROSS_CHECK_TOLERANCE_PCT", "5.0")
)
CAPEX_CROSS_CHECK_TOLERANCE_PCT: float = float(
    os.getenv("CAPEX_CROSS_CHECK_TOLERANCE_PCT", "5.0")
)
CAGR_WINDOW: int = 5
CFO_QUALITY_WINDOW: int = 5
CFO_QUALITY_MIN_VALID: int = 3

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging setup — edge cases go to ratio_edge_cases.log
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("populate_ratios")

edge_log_path = os.path.join(OUTPUT_DIR, "ratio_edge_cases.log")
edge_logger = logging.getLogger("ratio_edge_cases")
edge_logger.setLevel(logging.INFO)
if not edge_logger.handlers:
    fh = logging.FileHandler(edge_log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    edge_logger.addHandler(fh)


# ---------------------------------------------------------------------------
# Helper: safe float extraction from pandas value
# ---------------------------------------------------------------------------
def _f(val: Any) -> Optional[float]:
    """Return float or None; handles NaN/NaT/None uniformly."""
    if val is None:
        return None
    try:
        v = float(val)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _cal_year(year_str: str) -> Optional[int]:
    """Parse calendar year from 'YYYY-MM' or SENTINEL_TTM. Returns None for TTM."""
    if year_str == SENTINEL_TTM:
        return None
    try:
        return int(str(year_str)[:4])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-row CAGR: trailing 5yr window anchored at each row's fiscal year
# Bug #2 fix: compute for every row, not one scalar per company
# ---------------------------------------------------------------------------
def _compute_row_cagr(
    company_pnl_by_year: Dict[int, Dict],
    cal_year: int,
    metric: str,
    window: int = CAGR_WINDOW,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Compute trailing CAGR for a specific fiscal year using that year as window end.
    company_pnl_by_year: dict mapping cal_year -> row dict for one company.
    """
    start_year = cal_year - window
    end_row = company_pnl_by_year.get(cal_year)
    start_row = company_pnl_by_year.get(start_year)

    if end_row is None or start_row is None:
        return None, CagrFlag.INSUFFICIENT.value

    end_val = _f(end_row.get(metric))
    start_val = _f(start_row.get(metric))

    result = calculate_cagr(start_val, end_val, window)
    flag_str = result.flag.value if result.flag else None
    return result.value, flag_str


# ---------------------------------------------------------------------------
# Per-row rolling CFO quality score (trailing 5yr, min 3 valid)
# Consistent with cfo_quality_score() in cashflow_kpis.py
# ---------------------------------------------------------------------------
def _compute_row_cfo_quality(
    company_pnl_by_year: Dict[int, Dict],
    company_cf_by_year: Dict[int, Dict],
    cal_year: int,
    window: int = CFO_QUALITY_WINDOW,
) -> CfoQualityResult:
    """
    For a specific row year, gather trailing window years of (CFO, PAT) and
    call cfo_quality_score(). Returns CfoQualityResult(value, label, flag).
    """
    cfo_vals: List[Optional[float]] = []
    pat_vals: List[Optional[float]] = []

    for yr in range(cal_year - window + 1, cal_year + 1):
        pnl = company_pnl_by_year.get(yr)
        cf = company_cf_by_year.get(yr)
        cfo_vals.append(_f(cf["operating_activity"]) if cf else None)
        pat_vals.append(_f(pnl["net_profit"]) if pnl else None)

    return cfo_quality_score(cfo_vals, pat_vals)


# ---------------------------------------------------------------------------
# UPSERT SQL (SQLite ≥ 3.24, confirmed 3.45.3)
# Named-parameter dict binding — never positional (Bug fix: edge case directive)
# ---------------------------------------------------------------------------
UPSERT_SQL = """
INSERT INTO financial_ratios (
    id, company_id, year,
    net_profit_margin_pct, operating_profit_margin_pct, return_on_equity_pct,
    debt_to_equity, interest_coverage, asset_turnover,
    free_cash_flow_cr, capex_cr, cash_from_operations_cr,
    earnings_per_share, book_value_per_share, dividend_payout_ratio_pct, total_debt_cr,
    return_on_capital_employed_pct, return_on_assets_pct,
    net_debt_cr, icr_label, icr_at_risk_flag, high_leverage_flag,
    revenue_cagr_5yr, pat_cagr_5yr, eps_cagr_5yr,
    revenue_cagr_5yr_flag, pat_cagr_5yr_flag, eps_cagr_5yr_flag,
    composite_quality_score, composite_quality_score_flag, cfo_quality_label,
    cashflow_pattern_code, cashflow_pattern_label, pattern_flag,
    capex_intensity_label, capex_intensity_pct,
    fcf_conversion_flag, fcf_conversion_pct
)
VALUES (
    :id, :company_id, :year,
    :net_profit_margin_pct, :operating_profit_margin_pct, :return_on_equity_pct,
    :debt_to_equity, :interest_coverage, :asset_turnover,
    :free_cash_flow_cr, :capex_cr, :cash_from_operations_cr,
    :earnings_per_share, :book_value_per_share, :dividend_payout_ratio_pct, :total_debt_cr,
    :return_on_capital_employed_pct, :return_on_assets_pct,
    :net_debt_cr, :icr_label, :icr_at_risk_flag, :high_leverage_flag,
    :revenue_cagr_5yr, :pat_cagr_5yr, :eps_cagr_5yr,
    :revenue_cagr_5yr_flag, :pat_cagr_5yr_flag, :eps_cagr_5yr_flag,
    :composite_quality_score, :composite_quality_score_flag, :cfo_quality_label,
    :cashflow_pattern_code, :cashflow_pattern_label, :pattern_flag,
    :capex_intensity_label, :capex_intensity_pct,
    :fcf_conversion_flag, :fcf_conversion_pct
)
ON CONFLICT(company_id, year) DO UPDATE SET
    net_profit_margin_pct         = excluded.net_profit_margin_pct,
    operating_profit_margin_pct   = excluded.operating_profit_margin_pct,
    return_on_equity_pct          = excluded.return_on_equity_pct,
    debt_to_equity                = excluded.debt_to_equity,
    interest_coverage             = excluded.interest_coverage,
    asset_turnover                = excluded.asset_turnover,
    free_cash_flow_cr             = excluded.free_cash_flow_cr,
    capex_cr                      = excluded.capex_cr,
    cash_from_operations_cr       = excluded.cash_from_operations_cr,
    earnings_per_share            = excluded.earnings_per_share,
    book_value_per_share          = excluded.book_value_per_share,
    dividend_payout_ratio_pct     = excluded.dividend_payout_ratio_pct,
    total_debt_cr                 = excluded.total_debt_cr,
    return_on_capital_employed_pct= excluded.return_on_capital_employed_pct,
    return_on_assets_pct          = excluded.return_on_assets_pct,
    net_debt_cr                   = excluded.net_debt_cr,
    icr_label                     = excluded.icr_label,
    icr_at_risk_flag              = excluded.icr_at_risk_flag,
    high_leverage_flag            = excluded.high_leverage_flag,
    revenue_cagr_5yr              = excluded.revenue_cagr_5yr,
    pat_cagr_5yr                  = excluded.pat_cagr_5yr,
    eps_cagr_5yr                  = excluded.eps_cagr_5yr,
    revenue_cagr_5yr_flag         = excluded.revenue_cagr_5yr_flag,
    pat_cagr_5yr_flag             = excluded.pat_cagr_5yr_flag,
    eps_cagr_5yr_flag             = excluded.eps_cagr_5yr_flag,
    composite_quality_score       = excluded.composite_quality_score,
    composite_quality_score_flag  = excluded.composite_quality_score_flag,
    cfo_quality_label             = excluded.cfo_quality_label,
    cashflow_pattern_code         = excluded.cashflow_pattern_code,
    cashflow_pattern_label        = excluded.cashflow_pattern_label,
    pattern_flag                  = excluded.pattern_flag,
    capex_intensity_label         = excluded.capex_intensity_label,
    capex_intensity_pct           = excluded.capex_intensity_pct,
    fcf_conversion_flag           = excluded.fcf_conversion_flag,
    fcf_conversion_pct            = excluded.fcf_conversion_pct
"""


# ---------------------------------------------------------------------------
# Main population function
# ---------------------------------------------------------------------------
def populate_financial_ratios() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    log.info("=== Day 12: populate_financial_ratios started ===")

    # ------------------------------------------------------------------
    # Phase 1: Load all source data into memory (keyed by company_id)
    # ------------------------------------------------------------------
    log.info("Phase 1: Loading source tables into memory...")

    # P&L — primary anchor
    pnl_df = pd.read_sql_query(
        "SELECT * FROM profitandloss WHERE year != ?", conn, params=(SENTINEL_TTM,)
    )
    pnl_df["_cal_year"] = pnl_df["year"].apply(_cal_year)
    pnl_df = pnl_df.dropna(subset=["_cal_year"])
    pnl_df["_cal_year"] = pnl_df["_cal_year"].astype(int)

    # Balance Sheet
    bs_df = pd.read_sql_query(
        "SELECT * FROM balancesheet WHERE year != ?", conn, params=(SENTINEL_TTM,)
    )
    bs_df["_cal_year"] = bs_df["year"].apply(_cal_year)
    bs_df = bs_df.dropna(subset=["_cal_year"])
    bs_df["_cal_year"] = bs_df["_cal_year"].astype(int)

    # Cashflow
    cf_df = pd.read_sql_query(
        "SELECT * FROM cashflow WHERE year != ?", conn, params=(SENTINEL_TTM,)
    )
    cf_df["_cal_year"] = cf_df["year"].apply(_cal_year)
    cf_df = cf_df.dropna(subset=["_cal_year"])
    cf_df["_cal_year"] = cf_df["_cal_year"].astype(int)

    # Sectors (one row per company)
    sectors_df = pd.read_sql_query("SELECT company_id, broad_sector FROM sectors", conn)
    sectors_map: Dict[str, str] = dict(
        zip(sectors_df["company_id"], sectors_df["broad_sector"])
    )

    # Companies (for book_value and cross-check columns)
    companies_df = pd.read_sql_query(
        "SELECT id, book_value, roce_percentage, roe_percentage FROM companies", conn
    )
    companies_map: Dict[str, Dict] = {
        row["id"]: dict(row) for _, row in companies_df.iterrows()
    }

    # Pre-seeded capex_cr from financial_ratios (for cross-check, Bug fix pt.6)
    fr_preseeded = pd.read_sql_query(
        "SELECT company_id, year, capex_cr FROM financial_ratios", conn
    )
    fr_capex_map: Dict[Tuple[str, str], Optional[float]] = {
        (row["company_id"], row["year"]): _f(row["capex_cr"])
        for _, row in fr_preseeded.iterrows()
    }

    # ------------------------------------------------------------------
    # Bug #1 fix: UNION driver — all distinct (company_id, year) keys
    # from P&L, BS, and CF as the anchor (NOT financial_ratios table)
    # ------------------------------------------------------------------
    log.info("Phase 2: Building UNION driver from P&L + BS + CF...")

    pnl_keys = set(zip(pnl_df["company_id"], pnl_df["year"]))
    bs_keys = set(zip(bs_df["company_id"], bs_df["year"]))
    cf_keys = set(zip(cf_df["company_id"], cf_df["year"]))
    all_keys = pnl_keys | bs_keys | cf_keys
    log.info(
        f"Union driver: {len(all_keys)} distinct (company_id, year) pairs "
        f"[P&L={len(pnl_keys)}, BS={len(bs_keys)}, CF={len(cf_keys)}]"
    )

    # Build company-keyed lookup dicts for O(1) access
    def _build_lookup(df: pd.DataFrame) -> Dict[str, Dict[int, Dict]]:
        """Returns {company_id: {cal_year: row_dict}}"""
        result: Dict[str, Dict[int, Dict]] = defaultdict(dict)
        for _, row in df.iterrows():
            result[row["company_id"]][int(row["_cal_year"])] = row.to_dict()
        return result

    pnl_lookup = _build_lookup(pnl_df)
    bs_lookup = _build_lookup(bs_df)
    cf_lookup = _build_lookup(cf_df)

    # ------------------------------------------------------------------
    # Phase 3: Per-row KPI computation
    # ------------------------------------------------------------------
    log.info("Phase 3: Computing KPIs per row...")

    upsert_batch: List[Dict] = []
    capital_alloc_rows: List[Dict] = []
    errors = 0

    for company_id, year_str in sorted(all_keys):
        cal_yr = _cal_year(year_str)
        if cal_yr is None:
            continue

        pnl = pnl_lookup.get(company_id, {}).get(cal_yr)
        bs = bs_lookup.get(company_id, {}).get(cal_yr)
        cf = cf_lookup.get(company_id, {}).get(cal_yr)
        broad_sector = sectors_map.get(company_id, "")
        company_meta = companies_map.get(company_id, {})
        company_pnl_by_year = pnl_lookup.get(company_id, {})
        company_cf_by_year = cf_lookup.get(company_id, {})

        try:
            # ----- Direct-copy columns (Bug #4 fix) -----
            eps = _f(pnl["eps"]) if pnl else None
            bvps = _f(company_meta.get("book_value"))  # from companies table
            div_payout = _f(pnl["dividend_payout"]) if pnl else None
            total_debt = _f(bs["borrowings"]) if bs else None
            cfo_raw = _f(cf["operating_activity"]) if cf else None
            sales = _f(pnl["sales"]) if pnl else None

            # ----- Profitability ratios (Day 08) -----
            npm = net_profit_margin(_f(pnl["net_profit"]) if pnl else None, sales)
            opm = operating_profit_margin(
                _f(pnl["operating_profit"]) if pnl else None,
                sales,
                opm_pct_source=_f(pnl["opm_percentage"]) if pnl else None,
                company_id=company_id,
                year=year_str,
            )
            roe = return_on_equity(
                _f(pnl["net_profit"]) if pnl else None,
                _f(bs["equity_capital"]) if bs else None,
                _f(bs["reserves"]) if bs else None,
            )
            roce_result = return_on_capital_employed(
                _f(pnl["profit_before_tax"]) if pnl else None,
                _f(pnl["interest"]) if pnl else None,
                _f(bs["equity_capital"]) if bs else None,
                _f(bs["reserves"]) if bs else None,
                _f(bs["borrowings"]) if bs else None,
                broad_sector,
            )
            roa = return_on_assets(
                _f(pnl["net_profit"]) if pnl else None,
                _f(bs["total_assets"]) if bs else None,
            )

            # ----- Leverage & efficiency (Day 09) -----
            de_result = debt_to_equity(
                _f(bs["borrowings"]) if bs else None,
                _f(bs["equity_capital"]) if bs else None,
                _f(bs["reserves"]) if bs else None,
                broad_sector,
            )
            icr_result = interest_coverage_ratio(
                _f(pnl["operating_profit"]) if pnl else None,
                _f(pnl["other_income"]) if pnl else None,
                _f(pnl["interest"]) if pnl else None,
            )
            nd = net_debt(
                _f(bs["borrowings"]) if bs else None,
                _f(bs["investments"]) if bs else None,
            )
            at = asset_turnover(sales, _f(bs["total_assets"]) if bs else None)

            # ----- Cash flow KPIs (Day 11) -----
            fcf_res: FcfResult = free_cash_flow(
                cfo_raw,
                _f(cf["investing_activity"]) if cf else None,
            )
            cxi_res: CapexIntensityResult = capex_intensity(fcf_res.capex_cr, sales)
            fcf_conv_res: FcfConversionResult = fcf_conversion(
                fcf_res.value,
                _f(pnl["operating_profit"]) if pnl else None,
            )

            # Rolling CFO quality score per row (Bug #2 design, same as CAGR)
            cfo_qual: CfoQualityResult = _compute_row_cfo_quality(
                company_pnl_by_year, company_cf_by_year, cal_yr
            )

            # Pattern classifier — needs current CFO/PAT ratio for +-- split
            cfo_quality_ratio = (
                cfo_qual.value
            )  # None triggers Reinvestor (not Shareholder)
            pattern_res = classify_cashflow_pattern(
                cfo_raw,
                _f(cf["investing_activity"]) if cf else None,
                _f(cf["financing_activity"]) if cf else None,
                cfo_quality_ratio,
            )

            # ----- CAGR — per-row trailing 5yr (Bug #2 fix) -----
            rev_cagr, rev_flag = _compute_row_cagr(company_pnl_by_year, cal_yr, "sales")
            pat_cagr, pat_flag = _compute_row_cagr(
                company_pnl_by_year, cal_yr, "net_profit"
            )
            eps_cagr, eps_flag = _compute_row_cagr(company_pnl_by_year, cal_yr, "eps")

            # ----- Cross-checks (Phase 5 integrated per-row) -----
            # ROCE cross-check vs companies.roce_percentage
            src_roce = _f(company_meta.get("roce_percentage"))
            if roce_result.value is not None and src_roce is not None:
                diff = abs(roce_result.value - src_roce)
                if src_roce != 0:
                    pct_diff = abs(diff / src_roce) * 100
                    if pct_diff > ROCE_CROSS_CHECK_TOLERANCE_PCT:
                        edge_logger.info(
                            f"[ROCE_MISMATCH] {company_id}|{year_str}|"
                            f"computed={roce_result.value:.2f}|source={src_roce:.2f}|"
                            f"diff={pct_diff:.1f}% — category: to_be_triaged"
                        )

            # ROE cross-check vs companies.roe_percentage
            src_roe = _f(company_meta.get("roe_percentage"))
            if roe is not None and src_roe is not None:
                if src_roe != 0:
                    pct_diff = abs((roe - src_roe) / src_roe) * 100
                    if pct_diff > ROE_CROSS_CHECK_TOLERANCE_PCT:
                        edge_logger.info(
                            f"[ROE_MISMATCH] {company_id}|{year_str}|"
                            f"computed={roe:.2f}|source={src_roe:.2f}|"
                            f"diff={pct_diff:.1f}% — category: to_be_triaged"
                        )

            # CapEx cross-check vs pre-seeded capex_cr
            pre_capex = fr_capex_map.get((company_id, year_str))
            if fcf_res.capex_cr is not None and pre_capex is not None:
                msg = verify_capex_cross_check(
                    fcf_res.capex_cr, pre_capex, company_id, cal_yr
                )
                if msg:
                    edge_logger.info(
                        f"[CAPEX_MISMATCH] {msg} — category: formula_discrepancy"
                    )

            # ----- Build upsert dict (named params — never positional) -----
            row_id = f"{company_id}_{year_str}"
            record: Dict = {
                "id": row_id,
                "company_id": company_id,
                "year": year_str,
                # Direct copies
                "earnings_per_share": eps,
                "book_value_per_share": bvps,
                "dividend_payout_ratio_pct": div_payout,
                "total_debt_cr": total_debt,
                "cash_from_operations_cr": cfo_raw,
                # Profitability
                "net_profit_margin_pct": npm,
                "operating_profit_margin_pct": opm,
                "return_on_equity_pct": roe,
                "return_on_capital_employed_pct": roce_result.value,
                "return_on_assets_pct": roa,
                # Leverage
                "debt_to_equity": de_result.value if de_result else None,
                "high_leverage_flag": (
                    int(de_result.high_leverage_flag) if de_result else None
                ),
                "interest_coverage": icr_result.value,
                "icr_label": icr_result.label,
                "icr_at_risk_flag": (
                    int(icr_result.at_risk_flag)
                    if icr_result.at_risk_flag is not None
                    else None
                ),
                "net_debt_cr": nd,
                "asset_turnover": at,
                # Cash flow
                "free_cash_flow_cr": fcf_res.value,
                "capex_cr": fcf_res.capex_cr,
                "capex_intensity_pct": cxi_res.value,
                "capex_intensity_label": cxi_res.label,
                "fcf_conversion_pct": fcf_conv_res.value,
                "fcf_conversion_flag": fcf_conv_res.flag,
                # CFO quality
                "composite_quality_score": cfo_qual.value,
                "composite_quality_score_flag": cfo_qual.flag,
                "cfo_quality_label": cfo_qual.label,
                # Cashflow pattern
                "cashflow_pattern_code": (
                    pattern_res.pattern_code if pattern_res else None
                ),
                "cashflow_pattern_label": (
                    pattern_res.pattern_label if pattern_res else None
                ),
                "pattern_flag": pattern_res.pattern_flag if pattern_res else None,
                # CAGR
                "revenue_cagr_5yr": rev_cagr,
                "revenue_cagr_5yr_flag": rev_flag,
                "pat_cagr_5yr": pat_cagr,
                "pat_cagr_5yr_flag": pat_flag,
                "eps_cagr_5yr": eps_cagr,
                "eps_cagr_5yr_flag": eps_flag,
            }
            upsert_batch.append(record)

            # Capital allocation CSV record
            if pattern_res:
                capital_alloc_rows.append(
                    {
                        "company_id": company_id,
                        "year": year_str,
                        "cfo_sign": pattern_res.cfo_sign,
                        "cfi_sign": pattern_res.cfi_sign,
                        "cff_sign": pattern_res.cff_sign,
                        "pattern_code": pattern_res.pattern_code,
                        "pattern_label": pattern_res.pattern_label,
                        "pattern_flag": pattern_res.pattern_flag or "",
                    }
                )

        except Exception as exc:
            log.error(f"Row error [{company_id}|{year_str}]: {exc}", exc_info=True)
            errors += 1

    log.info(f"Phase 3 complete: {len(upsert_batch)} rows computed, {errors} errors")

    # ------------------------------------------------------------------
    # Phase 4: Atomic UPSERT in single transaction
    # ------------------------------------------------------------------
    log.info(f"Phase 4: Executing batch UPSERT ({len(upsert_batch)} rows)...")
    try:
        with conn:
            conn.executemany(UPSERT_SQL, upsert_batch)
        log.info("Phase 4 complete: UPSERT committed.")
    except Exception as exc:
        log.error(f"UPSERT failed: {exc}", exc_info=True)
        conn.close()
        sys.exit(1)

    # ------------------------------------------------------------------
    # Phase 5: Verification queries
    # ------------------------------------------------------------------
    log.info("Phase 5: Verification...")
    row_count = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    company_count = conn.execute(
        "SELECT COUNT(DISTINCT company_id) FROM financial_ratios"
    ).fetchone()[0]
    log.info(f"  financial_ratios row count     : {row_count}")
    log.info(f"  distinct companies             : {company_count}")

    # Check no column is entirely NULL
    null_only_cols = []
    key_cols = [
        "net_profit_margin_pct",
        "return_on_equity_pct",
        "return_on_capital_employed_pct",
        "revenue_cagr_5yr",
        "pat_cagr_5yr",
        "composite_quality_score",
        "cashflow_pattern_code",
        "capex_intensity_pct",
        "fcf_conversion_pct",
        "earnings_per_share",
        "book_value_per_share",
        "total_debt_cr",
    ]
    for col in key_cols:
        n = conn.execute(
            f"SELECT COUNT(*) FROM financial_ratios WHERE {col} IS NOT NULL"
        ).fetchone()[0]
        log.info(f"  {col}: {n} non-null")
        if n == 0:
            null_only_cols.append(col)

    if null_only_cols:
        log.warning(f"NULL-only columns (requires investigation): {null_only_cols}")
    else:
        log.info("  ✓ No null-only columns among key KPIs")

    if row_count < 1100:
        log.warning(
            f"  Row count {row_count} < 1100 exit criterion — check source data coverage"
        )
    else:
        log.info(f"  ✓ Row count {row_count} >= 1100 exit criterion met")

    if company_count < 92:
        log.warning(
            f"  Company count {company_count} < 92 — some companies missing entirely"
        )
    else:
        log.info(f"  ✓ Company count {company_count} >= 92")

    # ------------------------------------------------------------------
    # Phase 6: Emit capital_allocation.csv
    # ------------------------------------------------------------------
    log.info("Phase 6: Emitting capital_allocation.csv...")
    csv_path = os.path.join(OUTPUT_DIR, "capital_allocation.csv")
    fieldnames = [
        "company_id",
        "year",
        "cfo_sign",
        "cfi_sign",
        "cff_sign",
        "pattern_code",
        "pattern_label",
        "pattern_flag",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(capital_alloc_rows)
    log.info(
        f"  capital_allocation.csv written: {len(capital_alloc_rows)} rows → {csv_path}"
    )

    conn.close()
    log.info("=== Day 12 population complete ===")
    log.info(
        f"  Rows: {row_count} | Companies: {company_count} | "
        f"Errors: {errors} | CSV rows: {len(capital_alloc_rows)}"
    )


if __name__ == "__main__":
    populate_financial_ratios()
