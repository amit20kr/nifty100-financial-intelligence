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
import plotly.graph_objects as go
from src.dashboard.utils import db

st.set_page_config(page_title="Trend Analysis - Nifty 100 Analytics", layout="wide")
st.title("Trend Analysis")

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

st.subheader(f"Historical Trends: {id_to_name[company_id]}")

# Fetch data
df_pl = db.get_pl(company_id)
df_ratios = db.get_ratios(company_id)

if df_pl.empty or df_ratios.empty:
    st.warning("Insufficient financial data to display trends.")
    st.stop()

# Sort and filter to last 5 years
df_pl = df_pl.sort_values("year").tail(5)
df_ratios = df_ratios.sort_values("year").tail(5)

years_available = len(df_pl)

# KPIs and CAGR Overlays
latest_ratios = df_ratios.iloc[-1]
rev_cagr = latest_ratios.get("revenue_cagr_5yr", None)
pat_cagr = latest_ratios.get("pat_cagr_5yr", None)

col1, col2, col3 = st.columns(3)
col1.metric("Years of Data", f"{years_available} yrs")

if years_available < 5:
    col2.metric("Revenue 5Y CAGR", "N/A (Insufficient Data)")
    col3.metric("PAT 5Y CAGR", "N/A (Insufficient Data)")
    st.info(
        "CAGR metrics require 5 full years of history. This company was recently listed or data is missing."
    )
else:
    col2.metric("Revenue 5Y CAGR", f"{rev_cagr:.2f}%" if pd.notna(rev_cagr) else "N/A")
    col3.metric("PAT 5Y CAGR", f"{pat_cagr:.2f}%" if pd.notna(pat_cagr) else "N/A")

st.divider()

# Dual-axis Revenue & PAT Chart
st.subheader("Revenue & Net Profit Trend")
fig_rev_pat = go.Figure()
# Revenue Bar
fig_rev_pat.add_trace(
    go.Bar(
        x=df_pl["year"],
        y=df_pl["sales"],
        name="Revenue (Cr)",
        marker_color="rgb(55, 83, 109)",
    )
)
# Net Profit Line on secondary Y-axis not strictly necessary if we use dual-axis,
# but a side-by-side bar or overlaid line works. Let's use overlaid line without a secondary axis
# if PAT is much smaller, or just standard Bar since Plotly scales well.
fig_rev_pat.add_trace(
    go.Bar(
        x=df_pl["year"],
        y=df_pl["net_profit"],
        name="Net Profit (Cr)",
        marker_color="rgb(26, 118, 255)",
    )
)
fig_rev_pat.update_layout(
    barmode="group",
    xaxis_title="Year",
    yaxis_title="Amount (Cr)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
st.plotly_chart(fig_rev_pat, use_container_width=True)

col_eps, col_margins = st.columns(2)

with col_eps:
    st.subheader("Earnings Per Share (EPS)")
    fig_eps = px.line(df_pl, x="year", y="eps", markers=True, title="EPS Trend")
    fig_eps.update_traces(line_color="green")
    fig_eps.update_layout(xaxis_title="Year", yaxis_title="EPS (₹)")
    st.plotly_chart(fig_eps, use_container_width=True)

with col_margins:
    st.subheader("Profit Margins")
    fig_margins = go.Figure()
    if "opm_percentage" in df_pl.columns:
        fig_margins.add_trace(
            go.Scatter(
                x=df_pl["year"],
                y=df_pl["opm_percentage"],
                mode="lines+markers",
                name="Operating Profit Margin (%)",
            )
        )
    if "net_profit_margin_pct" in df_ratios.columns:
        fig_margins.add_trace(
            go.Scatter(
                x=df_ratios["year"],
                y=df_ratios["net_profit_margin_pct"],
                mode="lines+markers",
                name="Net Profit Margin (%)",
            )
        )
    fig_margins.update_layout(xaxis_title="Year", yaxis_title="Margin (%)")
    st.plotly_chart(fig_margins, use_container_width=True)
