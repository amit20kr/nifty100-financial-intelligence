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
import plotly.graph_objects as go
from src.dashboard.utils import db

st.set_page_config(page_title="Capital Allocation - Nifty 100 Analytics", layout="wide")
st.title("Capital Allocation")

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

st.subheader(f"Capital Flow & Debt: {id_to_name[company_id]}")

df_ratios = db.get_ratios(company_id)
if df_ratios.empty:
    st.warning("Insufficient financial data to display capital allocation.")
    st.stop()

# Sort chronological
df_ratios = df_ratios.sort_values("year").tail(10)

latest_ratios = df_ratios.iloc[-1]
cf_pattern = latest_ratios.get("cashflow_pattern_label", None)
capex_intensity = latest_ratios.get("capex_intensity_label", None)

# Graceful degradation for missing labels
if (
    pd.isna(cf_pattern)
    or pd.isna(capex_intensity)
    or cf_pattern == ""
    or capex_intensity == ""
):
    st.info(
        "No qualitative capital pattern available (Missing historical cashflow structure)"
    )
else:
    col1, col2 = st.columns(2)
    col1.metric("Cashflow Pattern", cf_pattern)
    col2.metric("Capex Intensity", capex_intensity)

st.divider()

col_cf, col_debt = st.columns(2)

with col_cf:
    st.subheader("Cashflow Generation vs Capex")
    fig_cf = go.Figure()

    # Operating Cash Flow
    if "cash_from_operations_cr" in df_ratios.columns:
        fig_cf.add_trace(
            go.Bar(
                x=df_ratios["year"],
                y=df_ratios["cash_from_operations_cr"],
                name="CFO (Cr)",
                marker_color="green",
            )
        )

    # Capex (usually negative in CF statement, but might be stored absolute. We plot as-is)
    if "capex_cr" in df_ratios.columns:
        # Let's assume capex is stored positive or negative, bar chart will handle it
        fig_cf.add_trace(
            go.Bar(
                x=df_ratios["year"],
                y=df_ratios["capex_cr"],
                name="Capex (Cr)",
                marker_color="red",
            )
        )

    # Free Cash Flow (Source of truth from ratios)
    if "free_cash_flow_cr" in df_ratios.columns:
        fig_cf.add_trace(
            go.Scatter(
                x=df_ratios["year"],
                y=df_ratios["free_cash_flow_cr"],
                mode="lines+markers",
                name="FCF (Cr)",
                line=dict(color="orange", width=3),
            )
        )

    fig_cf.update_layout(barmode="group", xaxis_title="Year", yaxis_title="Amount (Cr)")
    st.plotly_chart(fig_cf, use_container_width=True)


with col_debt:
    st.subheader("Leverage Trends")
    fig_debt = go.Figure()

    if "total_debt_cr" in df_ratios.columns:
        fig_debt.add_trace(
            go.Bar(
                x=df_ratios["year"],
                y=df_ratios["total_debt_cr"],
                name="Total Debt (Cr)",
                marker_color="gray",
            )
        )

    if "net_debt_cr" in df_ratios.columns:
        fig_debt.add_trace(
            go.Scatter(
                x=df_ratios["year"],
                y=df_ratios["net_debt_cr"],
                mode="lines+markers",
                name="Net Debt (Cr)",
                line=dict(color="blue", width=3),
            )
        )

    fig_debt.update_layout(
        barmode="overlay", xaxis_title="Year", yaxis_title="Amount (Cr)"
    )
    # Make bars partially transparent so line is clear
    fig_debt.update_traces(opacity=0.7, selector=dict(type="bar"))
    st.plotly_chart(fig_debt, use_container_width=True)
