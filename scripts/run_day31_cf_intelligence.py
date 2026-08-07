import os
import sys
import sqlite3
import pandas as pd
import logging

from dotenv import load_dotenv

# Ensure we can import from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analytics.cashflow_kpis import (
    cfo_quality_score,
    capex_intensity,
    fcf_conversion,
    bulk_compute_fcf_cagr,
    check_distress_signal,
    check_deleveraging,
)
from src.analytics.constants import CfoQualityScoreFlag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s \u2014 %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("day31_cf_intelligence")


def _extract_year(y_str: str) -> int:
    try:
        return int(str(y_str)[:4])
    except:
        return 0


def main():
    load_dotenv()

    db_path = "db/nifty100.db"
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        sys.exit(1)

    logger.info(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)

    # 1. Fetch tables
    comp_df = pd.read_sql("SELECT id FROM companies", conn)
    sec_df = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    fr_df = pd.read_sql("SELECT * FROM financial_ratios WHERE year != 'TTM'", conn)
    cf_df = pd.read_sql("SELECT * FROM cashflow WHERE year != 'TTM'", conn)
    pl_df = pd.read_sql("SELECT * FROM profitandloss WHERE year != 'TTM'", conn)
    bs_df = pd.read_sql("SELECT * FROM balancesheet WHERE year != 'TTM'", conn)

    # 2. Extract years for stable sorting and joining
    for df in [fr_df, cf_df, pl_df, bs_df]:
        if not df.empty:
            df["_year_int"] = df["year"].apply(_extract_year)

    # Compute bulk FCF CAGR
    fcf_cagr_results = bulk_compute_fcf_cagr(comp_df["id"].tolist(), db_path)

    sector_map = sec_df.set_index("company_id")["broad_sector"].to_dict()

    results = []
    distress_alerts = []

    for cid in comp_df["id"]:
        sector = sector_map.get(cid, "Unknown")

        c_fr = fr_df[fr_df["company_id"] == cid].sort_values("_year_int").copy()
        c_cf = cf_df[cf_df["company_id"] == cid].sort_values("_year_int").copy()
        c_pl = pl_df[pl_df["company_id"] == cid].sort_values("_year_int").copy()
        c_bs = bs_df[bs_df["company_id"] == cid].sort_values("_year_int").copy()

        # We need to evaluate CFO quality over 5 years.
        cfo_q_result = None
        if not c_fr.empty and not c_pl.empty:
            cfo_vals = c_fr["cash_from_operations_cr"].tolist()
            pat_vals = c_pl["net_profit"].tolist()
            # If lengths don't match, trim to shortest or join on year
            # Best is to join on year to ensure we match correctly
            merged = pd.merge(
                c_fr[["_year_int", "cash_from_operations_cr"]],
                c_pl[["_year_int", "net_profit", "sales"]],
                on="_year_int",
                how="inner",
            )

            cfo_q_result = cfo_quality_score(
                merged["cash_from_operations_cr"].tolist(),
                merged["net_profit"].tolist(),
            )
            cfo_quality_label = (
                cfo_q_result.label if cfo_q_result.label else cfo_q_result.flag
            )
        else:
            cfo_quality_label = CfoQualityScoreFlag.INSUFFICIENT_YEARS.value

        # Get latest year data for CapEx Intensity, Distress, Deleveraging
        cfo_quality_score_val = None
        capex_int_label = None
        capex_int_pct = None
        distress_flag = False
        deleveraging_flag = False
        cap_alloc_label = None
        cfo_val = None
        cff_val = None
        net_profit_val = None
        fcf_conv_pct = None

        if not c_fr.empty:
            latest_fr = c_fr.iloc[-1]
            cap_alloc_label = latest_fr.get("cashflow_pattern_label")

            if not c_cf.empty:
                latest_cf = c_cf.iloc[-1]
                cfo_val = latest_cf.get("operating_activity")
                cff_val = latest_cf.get("financing_activity")
                investing_activity = latest_cf.get("investing_activity")

                # CapEx is derived from investing activity per spec: abs(investing_activity) / sales * 100
                capex_val = (
                    abs(investing_activity)
                    if pd.notna(investing_activity) and investing_activity < 0
                    else 0.0
                )

                if not c_pl.empty:
                    latest_pl = c_pl.iloc[-1]
                    # Ensure years match
                    if latest_pl["_year_int"] == latest_cf["_year_int"]:
                        sales = latest_pl.get("sales")
                        net_profit_val = latest_pl.get("net_profit")
                        capex_res = capex_intensity(capex_val, sales)
                        capex_int_label = capex_res.label
                        capex_int_pct = (
                            round(capex_res.value, 4)
                            if capex_res.value is not None
                            else None
                        )

                        # FCF Conversion: FCF / Operating Profit * 100
                        fcf = (
                            cfo_val + investing_activity
                            if pd.notna(cfo_val) and pd.notna(investing_activity)
                            else None
                        )
                        op_profit = latest_pl.get("operating_profit")
                        fcf_conv_res = fcf_conversion(fcf, op_profit)
                        fcf_conv_pct = (
                            round(fcf_conv_res.value, 2)
                            if fcf_conv_res.value is not None
                            else None
                        )

                # Distress signal
                distress_flag = check_distress_signal(cfo_val, cff_val)

                if distress_flag:
                    distress_alerts.append(
                        {
                            "company_id": cid,
                            "cfo_value": cfo_val,
                            "cff_value": cff_val,
                            "latest_net_profit": net_profit_val,
                        }
                    )

                # Deleveraging check (requires prior year borrowings)
                if not c_bs.empty:
                    # Get latest year and previous year
                    if len(c_bs) >= 2:
                        # Find the row that corresponds to latest_cf
                        latest_bs = c_bs[c_bs["_year_int"] == latest_cf["_year_int"]]
                        prev_bs = c_bs[c_bs["_year_int"] == latest_cf["_year_int"] - 1]

                        if not latest_bs.empty and not prev_bs.empty:
                            curr_borrowing = latest_bs.iloc[0].get("borrowings")
                            prev_borrowing = prev_bs.iloc[0].get("borrowings")
                            del_res = check_deleveraging(
                                cff_val, prev_borrowing, curr_borrowing
                            )
                            deleveraging_flag = (
                                del_res if del_res is not None else False
                            )
                        else:
                            deleveraging_flag = False
                    else:
                        deleveraging_flag = False

        cagr_val, _ = fcf_cagr_results.get(cid, (None, None))

        results.append(
            {
                "company_id": cid,
                "sector": sector,
                "cfo_quality_score": (
                    round(cfo_q_result.value, 4)
                    if (not (c_fr.empty or c_pl.empty))
                    and cfo_q_result.value is not None
                    else None
                ),
                "cfo_quality_label": cfo_quality_label,
                "capex_intensity_pct": capex_int_pct,
                "capex_label": capex_int_label,
                "fcf_cagr_5yr": cagr_val,
                "fcf_conversion_pct": fcf_conv_pct,
                "distress_flag": distress_flag,
                "deleveraging_flag": deleveraging_flag,
                "capital_allocation_label": cap_alloc_label,
            }
        )

    conn.close()

    os.makedirs("output", exist_ok=True)

    # Save Intelligence Matrix
    res_df = pd.DataFrame(results)
    out_file = "output/cashflow_intelligence.xlsx"
    res_df.to_excel(out_file, index=False)
    logger.info(f"Successfully generated {out_file} with {len(res_df)} rows")

    # Save Distress Alerts
    alerts_df = pd.DataFrame(
        distress_alerts,
        columns=["company_id", "cfo_value", "cff_value", "latest_net_profit"],
    )
    alerts_file = "output/distress_alerts.csv"
    alerts_df.to_csv(alerts_file, index=False)
    logger.info(f"Successfully generated {alerts_file} with {len(alerts_df)} alerts")

    print("\n" + "=" * 60)
    print("DAY 31 \u2014 CASH FLOW INTELLIGENCE \u2014 SUMMARY")
    print("=" * 60)
    print(f"  Total Companies Processed : {len(res_df)}")
    print(f"  Distress Alerts Triggered : {len(alerts_df)}")
    print(f"  Deleveraging Flagged      : {res_df['deleveraging_flag'].sum()}")
    print("=" * 60)
    print("[DONE] Day 31 Complete")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
