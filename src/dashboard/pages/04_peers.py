# ── permanent path fix (must be first) ──────────────────────────────────────
# Uses an absolute file path so it works even before the project root is on
# sys.path (Streamlit's page runner strips the project root from sys.path).
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
import os
from src.dashboard.utils import db

st.set_page_config(page_title="Peer Comparison - Nifty 100 Analytics", layout="wide")
st.title("Peer Comparison")

peer_groups = db.get_peer_groups()
if not peer_groups:
    st.warning("No peer groups found in the database.")
    st.stop()

# Group Selection
selected_group = st.selectbox("Select Peer Group", options=peer_groups)

# Small sample warning logic
warnings_path = os.path.join(os.getcwd(), "output", "peer_group_warnings.csv")
if os.path.exists(warnings_path):
    warnings_df = pd.read_csv(warnings_path)
    if selected_group in warnings_df["peer_group_name"].values:
        st.warning(
            f"⚠️ Small Sample Warning: The '{selected_group}' peer group has fewer than 5 companies. Percentile rankings and averages may be statistically unreliable."
        )

# Fetch Data
df_peers = db.get_peer_percentiles(selected_group)

if df_peers.empty:
    st.info("No data available for this peer group.")
    st.stop()

# Company Selection for Radar
companies_in_group = df_peers["company_name"].unique()
selected_company = st.selectbox(
    "Select Company to compare vs Group Average", options=companies_in_group
)

# 8 Radar Metrics
radar_metrics = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "debt_to_equity",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "free_cash_flow_cr",
    "interest_coverage",
]

st.divider()
st.subheader("Percentile Radar Chart")
st.caption(
    "Plots the company's percentile rank against the peer group average percentile for each metric."
)

# Compute Averages
avg_percentiles = []
company_percentiles = []

for metric in radar_metrics:
    metric_data = df_peers[df_peers["metric"] == metric]

    # Group Average
    if not metric_data.empty:
        avg_rank = metric_data["percentile_rank"].mean() * 100
    else:
        avg_rank = 0
    avg_percentiles.append(avg_rank)

    # Company Value
    company_data = metric_data[metric_data["company_name"] == selected_company]
    if not company_data.empty and pd.notna(company_data.iloc[0]["percentile_rank"]):
        comp_rank = company_data.iloc[0]["percentile_rank"] * 100
    else:
        comp_rank = 0
    company_percentiles.append(comp_rank)

# Close the radar loop
radar_metrics_plot = radar_metrics + [radar_metrics[0]]
avg_percentiles_plot = avg_percentiles + [avg_percentiles[0]]
company_percentiles_plot = company_percentiles + [company_percentiles[0]]

fig = go.Figure()

fig.add_trace(
    go.Scatterpolar(
        r=avg_percentiles_plot,
        theta=radar_metrics_plot,
        fill="toself",
        name="Group Average",
        line=dict(color="rgba(200, 200, 200, 0.5)"),
        fillcolor="rgba(200, 200, 200, 0.2)",
    )
)

fig.add_trace(
    go.Scatterpolar(
        r=company_percentiles_plot,
        theta=radar_metrics_plot,
        fill="toself",
        name=selected_company,
        line=dict(color="royalblue"),
        fillcolor="rgba(65, 105, 225, 0.4)",
    )
)

fig.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    showlegend=True,
    height=500,
)

st.plotly_chart(fig, use_container_width=True)


st.divider()
st.subheader("Peer Group KPIs")


# Pivot table for display
# Rows = companies, Columns = metrics
# We display the raw `value`
# Handle Debt Free Edge Case
def get_display_value(row):
    if (
        row["metric"] == "interest_coverage"
        and pd.isna(row["value"])
        and row["percentile_rank"] == 1.0
    ):
        return "Debt Free"
    if pd.isna(row["value"]):
        return None
    # Format floats
    if isinstance(row["value"], float):
        return round(row["value"], 2)
    return row["value"]


df_display = df_peers.copy()
df_display["display_value"] = df_display.apply(get_display_value, axis=1)

# Pivot
pivot_df = df_display.pivot(
    index=["company_name", "company_id", "is_benchmark", "year", "year_mismatch_flag"],
    columns="metric",
    values="display_value",
).reset_index()

# Sort by benchmark first, then name
pivot_df = pivot_df.sort_values(
    by=["is_benchmark", "company_name"], ascending=[False, True]
)

# Drop company_id for UI
pivot_df = pivot_df.drop(columns=["company_id"])


# Apply styling
def highlight_benchmark(row):
    if row["is_benchmark"] == 1:
        return ["background-color: rgba(255, 215, 0, 0.2)"] * len(row)
    return [""] * len(row)


st.caption(
    "Note: Rows highlighted in yellow represent the benchmark company for this peer group."
)

styled_df = pivot_df.style.apply(highlight_benchmark, axis=1)

st.dataframe(styled_df, hide_index=True, use_container_width=True)

# Note on year_mismatch_flag
mismatches = pivot_df[pivot_df["year_mismatch_flag"] == 1]
if not mismatches.empty:
    st.info(
        f"**Note:** Some companies in this group (e.g. {mismatches.iloc[0]['company_name']}) have a `year_mismatch_flag=1`, indicating their latest data year ({mismatches.iloc[0]['year']}) does not perfectly align chronologically with the rest of the peer group. Compare with caution."
    )
