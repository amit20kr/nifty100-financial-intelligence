# ── permanent path fix (must be first) ──────────────────────────────────────
import importlib.util as _ilu
import pathlib as _pl

_ps = _pl.Path(__file__).resolve().parent.parent / "utils" / "path_setup.py"
_spec = _ilu.spec_from_file_location("path_setup", _ps)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
del _ilu, _pl, _ps, _spec, _mod  # clean up bootstrap names
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from src.dashboard.utils import db

st.set_page_config(page_title="Valuation - Nifty 100 Analytics", layout="wide")
st.title("Valuation Metrics")

df_companies = db.get_companies()
if df_companies.empty:
    st.warning("No company data available.")
    st.stop()

# Centralized Company Selection
id_to_name = dict(zip(df_companies["id"], df_companies["company_name"]))
options = list(id_to_name.keys())

if (
    "selected_company_id" not in st.session_state
    or st.session_state.selected_company_id not in options
):
    st.session_state.selected_company_id = options[0]

company_id = st.selectbox(
    "Select Company",
    options=options,
    format_func=lambda x: id_to_name.get(x, x),
    key="selected_company_id",
)

st.subheader(f"Valuation: {id_to_name[company_id]}")

# Fetch Valuation Data from the precomputed universe output
df_val = db.get_valuation(company_id)

if df_val.empty:
    st.warning(
        "Valuation data not yet generated. Please run `python src/analytics/valuation.py`."
    )
    st.stop()

val_data = df_val.iloc[0]

# Metrics
pe_ratio = val_data.get("pe_ratio")
pb_ratio = val_data.get("pb_ratio")
ev_ebitda = val_data.get("ev_ebitda")
fcf_yield = val_data.get("FCF_yield_pct")
med_5yr = val_data.get("5yr_median_PE")
pe_vs_sec = val_data.get("PE_vs_sector_median_pct")
flag = val_data.get("flag")

# Format flag visually
flag_color = "green" if flag == "Discount" else ("red" if flag == "Caution" else "blue")
if pd.notna(flag) and flag != "N/A":
    st.markdown(f"### Assessment: :{flag_color}[{flag}]")
else:
    st.markdown("### Assessment: N/A (Insufficient Data)")

st.divider()

col1, col2, col3, col4 = st.columns(4)


def fmt(v, suffix=""):
    return f"{v:.2f}{suffix}" if pd.notna(v) else "N/A"


# Delta for P/E compared to 5yr median (if available)
pe_delta_str = None
if pd.notna(pe_ratio) and pd.notna(med_5yr) and med_5yr > 0:
    pe_delta = ((pe_ratio / med_5yr) - 1) * 100
    pe_delta_str = f"{pe_delta:.1f}% vs 5yr Median"

col1.metric("P/E Ratio", fmt(pe_ratio, "x"), delta=pe_delta_str, delta_color="inverse")

col2.metric("P/B Ratio", fmt(pb_ratio, "x"))

col3.metric("EV / EBITDA", fmt(ev_ebitda, "x"))

col4.metric("FCF Yield", fmt(fcf_yield, "%"))

st.divider()

col_med, col_sec = st.columns(2)

with col_med:
    st.subheader("5-Year Median P/E")
    if pd.isna(med_5yr):
        st.info("Insufficient history (requires at least 3 years of valid P/E).")
    else:
        st.metric("5Yr Median", fmt(med_5yr, "x"))

with col_sec:
    st.subheader("Sector Relative Valuation")
    sec_pe = None
    if pd.notna(pe_ratio) and pd.notna(pe_vs_sec):
        # We can reconstruct sector median from the percentage
        sec_pe = pe_ratio / (1 + (pe_vs_sec / 100))
        st.metric(
            "Sector Median P/E",
            fmt(sec_pe, "x"),
            delta=f"{pe_vs_sec:.1f}% vs Sector",
            delta_color="inverse",
        )
    else:
        st.info("No valid sector median available.")

st.divider()

# Historical Trends
st.subheader("Historical Valuation Trend")
df_mc = pd.DataFrame()
with sqlite3.connect("db/nifty100.db") as conn:
    df_mc = pd.read_sql_query(
        "SELECT year, pe_ratio, pb_ratio FROM market_cap WHERE company_id = ? ORDER BY year ASC",
        conn,
        params=(company_id,),
    )

if not df_mc.empty:
    fig = px.line(
        df_mc,
        x="year",
        y=["pe_ratio", "pb_ratio"],
        markers=True,
        title="P/E and P/B Trends",
    )
    fig.update_layout(xaxis_title="Year", yaxis_title="Multiple (x)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No historical market cap data available.")
