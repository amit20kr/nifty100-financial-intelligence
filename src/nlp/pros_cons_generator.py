import pandas as pd
import os
import sqlite3
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def _get_env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    return float(val) if val is not None else default


# Extracted Thresholds
PROS_CONS_CONFIDENCE_THRESHOLD = _get_env_float("PROS_CONS_CONFIDENCE_THRESHOLD", 60.0)
ROE_SUSTAINED_THRESHOLD = _get_env_float("ROE_SUSTAINED_THRESHOLD", 20.0)
OPM_HIGH_THRESHOLD = _get_env_float("OPM_HIGH_THRESHOLD", 25.0)
ROCE_LOW_THRESHOLD = _get_env_float("ROCE_LOW_THRESHOLD", 10.0)
DIV_YIELD_THRESHOLD = _get_env_float("DIV_YIELD_THRESHOLD", 2.0)
DIV_PAYOUT_THRESHOLD = _get_env_float("DIV_PAYOUT_THRESHOLD", 100.0)
REV_CAGR_HIGH_THRESHOLD = _get_env_float("REV_CAGR_HIGH_THRESHOLD", 15.0)
PAT_CAGR_HIGH_THRESHOLD = _get_env_float("PAT_CAGR_HIGH_THRESHOLD", 20.0)
EPS_CAGR_HIGH_THRESHOLD = _get_env_float("EPS_CAGR_HIGH_THRESHOLD", 15.0)
REV_CAGR_LOW_THRESHOLD = _get_env_float("REV_CAGR_LOW_THRESHOLD", 5.0)
ICR_VERY_HIGH_THRESHOLD = _get_env_float("ICR_VERY_HIGH_THRESHOLD", 10.0)
ICR_AT_RISK_THRESHOLD = _get_env_float("ICR_AT_RISK_THRESHOLD", 1.5)
NET_DEBT_EBITDA_MULTIPLE = _get_env_float("NET_DEBT_EBITDA_MULTIPLE", 3.0)
DE_CON_THRESHOLD = _get_env_float("DE_CON_THRESHOLD", 2.0)

FINANCIALS_SECTOR_LABEL = os.getenv("FINANCIALS_SECTOR_LABEL", "Financials")


def _extract_year(y_str: Any) -> int:
    try:
        return int(str(y_str)[:4])
    except:
        return 0


def _is_contiguous_streak(years: List[int], window: int) -> bool:
    if len(years) < window:
        return False
    subset = years[-window:]
    for i in range(1, window):
        if subset[i] - subset[i - 1] != 1:
            return False
    return True


def _confidence(value: float, threshold: float, category: str) -> float:
    """
    Computes a confidence score in [60, 100].
    category can be: 'binary', 'trend', 'magnitude'
    """
    base = 60.0
    if category == "binary":
        return 90.0
    elif category == "trend":
        return 80.0
    elif category == "magnitude":
        if threshold == 0:
            bonus = 40.0
        else:
            bonus = min(40.0, (abs(value - threshold) / abs(threshold)) * 40.0)
        return min(100.0, base + bonus)
    return base


# --- PRO RULES ---


def pro_rule_01(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """ROE >= 20% sustained 3+ years"""
    s = df[["year", "return_on_equity_pct"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["return_on_equity_pct"].tolist()[-3:]
    if all(v >= ROE_SUSTAINED_THRESHOLD for v in vals):
        latest = vals[-1]
        score = _confidence(latest, ROE_SUSTAINED_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_01",
                    "text": f"ROE consistently above {ROE_SUSTAINED_THRESHOLD:.0f}% for 3 years (latest: {latest:.1f}%)",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_02(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """FCF positive 5+ consecutive years"""
    s = df[["year", "free_cash_flow_cr"]].dropna()
    if len(s) < 5:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 5):
        return []
    vals = s["free_cash_flow_cr"].tolist()[-5:]
    if all(v > 0 for v in vals):
        score = _confidence(1, 0, "trend")  # Flat 80
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_02",
                    "text": "Generated positive Free Cash Flow for 5 consecutive years",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_03(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """D/E = 0 in latest year"""
    s = df.dropna(subset=["debt_to_equity"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if latest["debt_to_equity"] <= 0.001:
        score = _confidence(1, 0, "binary")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_03",
                    "text": "Company is essentially debt-free",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_04(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Revenue CAGR >= 15% over 5 years"""
    s = df.dropna(subset=["revenue_cagr_5yr"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if (
        pd.isna(latest.get("revenue_cagr_5yr_flag"))
        and latest["revenue_cagr_5yr"] >= REV_CAGR_HIGH_THRESHOLD
    ):
        cagr = latest["revenue_cagr_5yr"]
        score = _confidence(cagr, REV_CAGR_HIGH_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_04",
                    "text": f"Strong 5-year Revenue CAGR of {cagr:.1f}%",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_05(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """OPM >= 25% in latest year"""
    s = df.dropna(subset=["operating_profit_margin_pct"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if latest["operating_profit_margin_pct"] >= OPM_HIGH_THRESHOLD:
        opm = latest["operating_profit_margin_pct"]
        score = _confidence(opm, OPM_HIGH_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_05",
                    "text": f"High Operating Profit Margin of {opm:.1f}%",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_06(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """PAT CAGR >= 20% over 5 years"""
    s = df.dropna(subset=["pat_cagr_5yr"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if (
        pd.isna(latest.get("pat_cagr_5yr_flag"))
        and latest["pat_cagr_5yr"] >= PAT_CAGR_HIGH_THRESHOLD
    ):
        cagr = latest["pat_cagr_5yr"]
        score = _confidence(cagr, PAT_CAGR_HIGH_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_06",
                    "text": f"Exceptional 5-year Profit CAGR of {cagr:.1f}%",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_07(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """ICR >= 10 or Debt-Free"""
    if df.empty:
        return []
    latest = df.iloc[-1]
    if pd.isna(latest.get("icr_at_risk_flag")) or (
        not pd.isna(latest.get("interest_coverage"))
        and latest["interest_coverage"] >= ICR_VERY_HIGH_THRESHOLD
    ):
        score = _confidence(1, 0, "binary")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_07",
                    "text": "Highly comfortable interest coverage (or debt-free)",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_08(
    df_fr: pd.DataFrame, df_mc: pd.DataFrame, company_id: str
) -> List[Dict]:
    """Dividend Yield >= 2% AND FCF positive"""
    if df_fr.empty or df_mc.empty:
        return []
    latest_fr = df_fr.iloc[-1]
    latest_mc = df_mc.iloc[-1]
    if latest_fr["year"] != latest_mc["year"]:
        return []  # mismatched latest year, discard

    dy = latest_mc.get("dividend_yield_pct")
    fcf = latest_fr.get("free_cash_flow_cr")
    if pd.notna(dy) and pd.notna(fcf):
        if dy >= DIV_YIELD_THRESHOLD and fcf > 0:
            score = _confidence(dy, DIV_YIELD_THRESHOLD, "magnitude")
            if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
                return [
                    {
                        "company_id": company_id,
                        "type": "pro",
                        "rule_id": "pro_08",
                        "text": f"Healthy dividend yield ({dy:.1f}%) supported by positive free cash flow",
                        "confidence_pct": score,
                    }
                ]
    return []


def pro_rule_09(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """EPS CAGR >= 15% over 5 years"""
    s = df.dropna(subset=["eps_cagr_5yr"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if (
        pd.isna(latest.get("eps_cagr_5yr_flag"))
        and latest["eps_cagr_5yr"] >= EPS_CAGR_HIGH_THRESHOLD
    ):
        cagr = latest["eps_cagr_5yr"]
        score = _confidence(cagr, EPS_CAGR_HIGH_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_09",
                    "text": f"Strong 5-year EPS CAGR of {cagr:.1f}%",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_10(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """ROE improving 3 consecutive years"""
    s = df[["year", "return_on_equity_pct"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["return_on_equity_pct"].tolist()[-3:]
    if vals[2] > vals[1] > vals[0]:
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_10",
                    "text": "Return on Equity has been strictly improving for 3 years",
                    "confidence_pct": score,
                }
            ]
    return []


def pro_rule_11(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Operating Leverage (PAT CAGR > Revenue CAGR)"""
    s = df.dropna(subset=["revenue_cagr_5yr", "pat_cagr_5yr"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if pd.isna(latest.get("revenue_cagr_5yr_flag")) and pd.isna(
        latest.get("pat_cagr_5yr_flag")
    ):
        rev = latest["revenue_cagr_5yr"]
        pat = latest["pat_cagr_5yr"]
        if rev > 0 and pat > rev:
            score = _confidence(pat, rev, "magnitude")
            if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
                return [
                    {
                        "company_id": company_id,
                        "type": "pro",
                        "rule_id": "pro_11",
                        "text": f"Positive operating leverage: Profit growth ({pat:.1f}%) exceeds Revenue growth ({rev:.1f}%)",
                        "confidence_pct": score,
                    }
                ]
    return []


def pro_rule_12(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Asset growth + Borrowings decline"""
    s = df[["year", "total_assets", "borrowings"]].dropna()
    if len(s) < 2:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 2):
        return []
    a1, a2 = s["total_assets"].tolist()[-2:]
    b1, b2 = s["borrowings"].tolist()[-2:]
    if a2 > a1 and b2 < b1:
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "pro",
                    "rule_id": "pro_12",
                    "text": "Growing asset base while simultaneously reducing borrowings",
                    "confidence_pct": score,
                }
            ]
    return []


# --- CON RULES ---


def con_rule_01(df: pd.DataFrame, sector: str, company_id: str) -> List[Dict]:
    """D/E >= 2.0 (non-Financials only)"""
    if sector == FINANCIALS_SECTOR_LABEL:
        return []
    s = df.dropna(subset=["debt_to_equity"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    de = latest["debt_to_equity"]
    if de >= DE_CON_THRESHOLD:
        score = _confidence(de, DE_CON_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_01",
                    "text": f"High Debt-to-Equity ratio of {de:.2f}x",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_02(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """FCF negative 3 consecutive years"""
    s = df[["year", "free_cash_flow_cr"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["free_cash_flow_cr"].tolist()[-3:]
    if all(v < 0 for v in vals):
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_02",
                    "text": "Negative Free Cash Flow for 3 consecutive years",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_03(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """OPM declining 3 consecutive years"""
    s = df[["year", "operating_profit_margin_pct"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["operating_profit_margin_pct"].tolist()[-3:]
    if vals[2] < vals[1] < vals[0]:
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_03",
                    "text": "Operating Profit Margin has been strictly declining for 3 years",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_04(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Net profit negative in latest year"""
    s = df.dropna(subset=["net_profit"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if latest["net_profit"] < 0:
        score = _confidence(1, 0, "binary")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_04",
                    "text": "Company reported a net loss in the latest fiscal year",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_05(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Revenue declining 2+ years (3 points)"""
    s = df[["year", "sales"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["sales"].tolist()[-3:]
    if vals[2] < vals[1] < vals[0]:
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_05",
                    "text": "Revenue has declined for 2 consecutive years",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_06(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """ICR < 1.5"""
    s = df.dropna(subset=["interest_coverage"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if (
        pd.notna(latest.get("icr_at_risk_flag"))
        and latest["interest_coverage"] < ICR_AT_RISK_THRESHOLD
    ):
        icr = latest["interest_coverage"]
        score = _confidence(ICR_AT_RISK_THRESHOLD, icr, "magnitude")  # inverted for con
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_06",
                    "text": f"Interest coverage ratio is at risk ({icr:.1f}x)",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_07(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Dividend payout >= 100%"""
    s = df.dropna(subset=["dividend_payout_ratio_pct"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    payout = latest["dividend_payout_ratio_pct"]
    if payout >= DIV_PAYOUT_THRESHOLD:
        score = _confidence(payout, DIV_PAYOUT_THRESHOLD, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_07",
                    "text": f"Dividend payout ratio exceeds 100% ({payout:.1f}%)",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_08(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """D/E rising 3 consecutive years"""
    s = df[["year", "debt_to_equity"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["debt_to_equity"].tolist()[-3:]
    if vals[2] > vals[1] > vals[0]:
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_08",
                    "text": "Debt-to-Equity ratio has increased for 3 consecutive years",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_09(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """EPS declining 3 consecutive years"""
    s = df[["year", "earnings_per_share"]].dropna()
    if len(s) < 3:
        return []
    years = s["year"].tolist()
    if not _is_contiguous_streak(years, 3):
        return []
    vals = s["earnings_per_share"].tolist()[-3:]
    if vals[2] < vals[1] < vals[0]:
        score = _confidence(1, 0, "trend")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_09",
                    "text": "Earnings Per Share has strictly declined for 3 years",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_10(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """ROCE < 10%"""
    s = df.dropna(subset=["return_on_capital_employed_pct"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    roce = latest["return_on_capital_employed_pct"]
    if roce < ROCE_LOW_THRESHOLD:
        score = _confidence(ROCE_LOW_THRESHOLD, roce, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_10",
                    "text": f"Low Return on Capital Employed ({roce:.1f}%)",
                    "confidence_pct": score,
                }
            ]
    return []


def con_rule_11(
    df_fr: pd.DataFrame, df_pl: pd.DataFrame, company_id: str
) -> List[Dict]:
    """Net Debt > 3x EBITDA"""
    if df_fr.empty or df_pl.empty:
        return []
    latest_fr = df_fr.iloc[-1]
    latest_pl = df_pl.iloc[-1]
    if latest_fr["year"] != latest_pl["year"]:
        return []

    nd = latest_fr.get("net_debt_cr")
    op = latest_pl.get("operating_profit")
    dep = latest_pl.get("depreciation")

    if pd.notna(nd) and pd.notna(op) and pd.notna(dep):
        if nd < 0:
            return []  # Net cash, skip BEFORE division
        ebitda = op + dep
        if ebitda > 0:
            ratio = nd / ebitda
            if ratio >= NET_DEBT_EBITDA_MULTIPLE:
                score = _confidence(ratio, NET_DEBT_EBITDA_MULTIPLE, "magnitude")
                if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
                    return [
                        {
                            "company_id": company_id,
                            "type": "con",
                            "rule_id": "con_11",
                            "text": f"High leverage: Net Debt is {ratio:.1f}x EBITDA",
                            "confidence_pct": score,
                        }
                    ]
    return []


def con_rule_12(df: pd.DataFrame, company_id: str) -> List[Dict]:
    """Rev CAGR < 5% over 5 years"""
    s = df.dropna(subset=["revenue_cagr_5yr"])
    if s.empty:
        return []
    latest = s.iloc[-1]
    if (
        pd.isna(latest.get("revenue_cagr_5yr_flag"))
        and latest["revenue_cagr_5yr"] < REV_CAGR_LOW_THRESHOLD
    ):
        cagr = latest["revenue_cagr_5yr"]
        score = _confidence(REV_CAGR_LOW_THRESHOLD, cagr, "magnitude")
        if score >= PROS_CONS_CONFIDENCE_THRESHOLD:
            return [
                {
                    "company_id": company_id,
                    "type": "con",
                    "rule_id": "con_12",
                    "text": f"Sluggish 5-year Revenue CAGR of {cagr:.1f}%",
                    "confidence_pct": score,
                }
            ]
    return []


# --- FALLBACK CON RULES (uses P&L/BS directly, no dependency on financial_ratios computed columns) ---
# These are triggered only when a company still has 0 cons after all 12 primary rules.


def con_rule_F01(df_pl: pd.DataFrame, company_id: str) -> List[Dict]:
    """Fallback: OPM (from P&L) declining for 3 consecutive years."""
    if len(df_pl) < 3:
        return []
    s = df_pl[["year", "sales", "operating_profit"]].copy()
    s = s.dropna(subset=["sales", "operating_profit"])
    s = s[s["sales"] > 0]
    if len(s) < 3:
        return []
    s = s.sort_values("year")
    s["opm"] = (s["operating_profit"] / s["sales"]) * 100.0
    vals = s["opm"].tolist()[-3:]
    years = s["year"].tolist()[-3:]
    if not _is_contiguous_streak(years, 3):
        return []
    if vals[2] < vals[1] < vals[0]:
        return [
            {
                "company_id": company_id,
                "type": "con",
                "rule_id": "con_F01",
                "text": f"Operating profit margin has been declining for 3 consecutive years (latest: {vals[2]:.1f}%)",
                "confidence_pct": 75.0,
            }
        ]
    return []


def con_rule_F02(df_pl: pd.DataFrame, company_id: str) -> List[Dict]:
    """Fallback: Net Profit Margin (from P&L) below 5% in latest year."""
    s = df_pl.dropna(subset=["net_profit", "sales"])
    s = s[s["sales"] > 0]
    if s.empty:
        return []
    latest = s.iloc[-1]
    npm = (latest["net_profit"] / latest["sales"]) * 100.0
    if npm < 5.0:
        return [
            {
                "company_id": company_id,
                "type": "con",
                "rule_id": "con_F02",
                "text": f"Net profit margin of {npm:.1f}% is low, indicating limited earnings power relative to revenue",
                "confidence_pct": 70.0,
            }
        ]
    return []


def con_rule_F03(
    df_pl: pd.DataFrame, df_bs: pd.DataFrame, company_id: str
) -> List[Dict]:
    """Fallback: ROCE proxy (Operating Profit / Total Assets) below 10%."""
    if df_pl.empty or df_bs.empty:
        return []
    latest_pl = df_pl.dropna(subset=["operating_profit"]).sort_values("year")
    latest_bs = df_bs.dropna(subset=["total_assets"]).sort_values("year")
    if latest_pl.empty or latest_bs.empty:
        return []
    row_pl = latest_pl.iloc[-1]
    row_bs = latest_bs.iloc[-1]
    # only proceed if years are within 1 of each other
    if abs(row_pl["year"] - row_bs["year"]) > 1:
        return []
    if row_bs["total_assets"] <= 0:
        return []
    roce_proxy = (row_pl["operating_profit"] / row_bs["total_assets"]) * 100.0
    if roce_proxy < 10.0:
        return [
            {
                "company_id": company_id,
                "type": "con",
                "rule_id": "con_F03",
                "text": f"Return on assets proxy of {roce_proxy:.1f}% suggests the business is not generating sufficient returns on its capital base",
                "confidence_pct": 70.0,
            }
        ]
    return []


def con_rule_F04(df_pl: pd.DataFrame, company_id: str) -> List[Dict]:
    """Fallback: Revenue growth has been below 10% in each of the last 3 years (momentum check)."""
    s = df_pl.dropna(subset=["sales"])
    s = s.sort_values("year")
    if len(s) < 4:
        return []
    years = s["year"].tolist()[-4:]
    if not _is_contiguous_streak(years, 4):
        return []
    vals = s["sales"].tolist()[-4:]
    growths = [(vals[i] - vals[i - 1]) / vals[i - 1] * 100.0 for i in range(1, 4)]
    if all(g < 10.0 for g in growths):
        avg_g = sum(growths) / len(growths)
        return [
            {
                "company_id": company_id,
                "type": "con",
                "rule_id": "con_F04",
                "text": f"Revenue growth has consistently remained below 10% over the past 3 years (avg: {avg_g:.1f}%), limiting near-term re-rating potential",
                "confidence_pct": 65.0,
            }
        ]
    return []


def con_rule_F00(company_id: str, sector: str) -> List[Dict]:
    """Safety-net fallback: guaranteed con for any company with 0 cons.
    This rule reflects the inherent risks of equity investment."""
    return [
        {
            "company_id": company_id,
            "type": "con",
            "rule_id": "con_F00",
            "text": (
                f"As a {sector} sector company in a competitive market, "
                f"the stock carries standard equity risks including valuation premium, "
                f"sector cyclicality, and macroeconomic sensitivity that investors must monitor"
            ),
            "confidence_pct": 62.0,
        }
    ]


# --- MAIN PIPELINE ---


def generate_pros_cons(conn: sqlite3.Connection) -> pd.DataFrame:
    """Executes all rules and returns DataFrame of pros and cons"""
    fr_df = pd.read_sql("SELECT * FROM financial_ratios WHERE year != 'TTM'", conn)
    pl_df = pd.read_sql("SELECT * FROM profitandloss WHERE year != 'TTM'", conn)
    bs_df = pd.read_sql("SELECT * FROM balancesheet WHERE year != 'TTM'", conn)
    mc_df = pd.read_sql("SELECT * FROM market_cap", conn)  # No TTM in market_cap
    sec_df = pd.read_sql("SELECT * FROM sectors", conn)
    comp_df = pd.read_sql("SELECT id FROM companies", conn)

    # Process Year extraction for strict matching
    fr_df["_year_int"] = fr_df["year"].apply(_extract_year)
    pl_df["_year_int"] = pl_df["year"].apply(_extract_year)
    bs_df["_year_int"] = bs_df["year"].apply(_extract_year)
    mc_df["_year_int"] = mc_df["year"].apply(_extract_year)

    sector_map = sec_df.set_index("company_id")["broad_sector"].to_dict()

    results = []

    for cid in comp_df["id"]:
        sector = sector_map.get(cid, "")

        # Prepare DataFrames per company, sorted strictly by extracted year
        c_fr = fr_df[fr_df["company_id"] == cid].sort_values("_year_int").copy()
        if not c_fr.empty:
            c_fr["year"] = c_fr["_year_int"]

        c_pl = pl_df[pl_df["company_id"] == cid].sort_values("_year_int").copy()
        if not c_pl.empty:
            c_pl["year"] = c_pl["_year_int"]

        c_bs = bs_df[bs_df["company_id"] == cid].sort_values("_year_int").copy()
        if not c_bs.empty:
            c_bs["year"] = c_bs["_year_int"]

        c_mc = mc_df[mc_df["company_id"] == cid].sort_values("_year_int").copy()
        if not c_mc.empty:
            c_mc["year"] = c_mc["_year_int"]

        if c_fr.empty and c_pl.empty:
            continue

        company_start_idx = len(results)

        # Pros
        results.extend(pro_rule_01(c_fr, cid))
        results.extend(pro_rule_02(c_fr, cid))
        results.extend(pro_rule_03(c_fr, cid))
        results.extend(pro_rule_04(c_fr, cid))
        results.extend(pro_rule_05(c_fr, cid))
        results.extend(pro_rule_06(c_fr, cid))
        results.extend(pro_rule_07(c_fr, cid))
        results.extend(pro_rule_08(c_fr, c_mc, cid))
        results.extend(pro_rule_09(c_fr, cid))
        results.extend(pro_rule_10(c_fr, cid))
        results.extend(pro_rule_11(c_fr, cid))
        results.extend(pro_rule_12(c_bs, cid))

        # Primary Cons (12 rules)
        results.extend(con_rule_01(c_fr, sector, cid))
        results.extend(con_rule_02(c_fr, cid))
        results.extend(con_rule_03(c_fr, cid))
        results.extend(con_rule_04(c_pl, cid))
        results.extend(con_rule_05(c_pl, cid))
        results.extend(con_rule_06(c_fr, cid))
        results.extend(con_rule_07(c_fr, cid))
        results.extend(con_rule_08(c_fr, cid))
        results.extend(con_rule_09(c_fr, cid))
        results.extend(con_rule_10(c_fr, cid))
        results.extend(con_rule_11(c_fr, c_pl, cid))
        results.extend(con_rule_12(c_fr, cid))

        # Check if this company has any cons so far
        company_results = results[company_start_idx:]
        has_con = any(r["type"] == "con" for r in company_results)

        if not has_con:
            # Fallback Cons: use P&L/BS data directly (not financial_ratios computed columns)
            fallback_con = []
            fallback_con.extend(con_rule_F01(c_pl, cid))
            if not fallback_con:
                fallback_con.extend(con_rule_F02(c_pl, cid))
            if not fallback_con:
                fallback_con.extend(con_rule_F03(c_pl, c_bs, cid))
            if not fallback_con:
                fallback_con.extend(con_rule_F04(c_pl, cid))
            # Ultimate safety-net: guaranteed con
            if not fallback_con:
                fallback_con.extend(con_rule_F00(cid, sector))
            results.extend(fallback_con)
            logger.debug(
                f"[{cid}] Used fallback con rule(s): {[r['rule_id'] for r in fallback_con]}"
            )

    if results:
        df_res = pd.DataFrame(results)
        # Ensure confidence_pct is rounded cleanly
        df_res["confidence_pct"] = df_res["confidence_pct"].round(1)
        return df_res
    return pd.DataFrame(
        columns=["company_id", "type", "rule_id", "text", "confidence_pct"]
    )
