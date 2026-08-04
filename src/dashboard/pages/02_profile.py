# ── permanent path fix (must be first) ──────────────────────────────────────
# Uses an absolute file path so it works even before the project root is on
# sys.path (Streamlit's page runner strips the project root from sys.path).
import importlib.util as _ilu, pathlib as _pl
_ps = _pl.Path(__file__).resolve().parent.parent / "utils" / "path_setup.py"
_spec = _ilu.spec_from_file_location("path_setup", _ps)
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
del _ilu, _pl, _ps, _spec, _mod  # clean up bootstrap names
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from src.dashboard.utils import db

st.set_page_config(page_title="Company Profile - Nifty 100 Analytics", layout="wide")
st.title("Company Profile")

df_companies = db.get_companies()
if df_companies.empty:
    st.warning("No company data available.")
    st.stop()

# Build mapping for selectbox
id_to_name = dict(zip(df_companies['id'], df_companies['company_name']))
options = list(id_to_name.keys())

# Initialize session state if empty
if 'selected_company_id' not in st.session_state or st.session_state.selected_company_id not in options:
    st.session_state.selected_company_id = options[0]

# Search Component linked to session state
company_id = st.selectbox(
    "Search Company", 
    options=options, 
    format_func=lambda x: id_to_name.get(x, x),
    key="selected_company_id"
)
company_data = df_companies[df_companies['id'] == company_id].iloc[0]

# Company Card
st.subheader(company_data['company_name'])

# Extract NSE Ticker
nse_profile = company_data.get('nse_profile')
nse_ticker = "N/A"
if pd.notna(nse_profile) and nse_profile:
    try:
        if "symbol=" in nse_profile:
            nse_ticker = nse_profile.split("symbol=")[-1].strip()
    except Exception:
        pass

# Get sector info
df_sectors = db.get_sectors()
sector_info = "N/A"
sub_sector_info = "N/A"
if not df_sectors.empty:
    sec_data = df_sectors[df_sectors['company_id'] == company_id]
    if not sec_data.empty:
        sector_info = sec_data.iloc[0]['broad_sector']
        sub_sector_info = sec_data.iloc[0]['sub_sector']

st.markdown(f"**Sector:** {sector_info} | **Sub-Sector:** {sub_sector_info} | **NSE Ticker:** {nse_ticker}")
st.write(company_data.get('about_company', "No description available."))

st.divider()

# KPIs
df_ratios_full = db.get_ratios(company_id)
if not df_ratios_full.empty:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    def fmt(val, suffix=""):
        if pd.isna(val) or val is None:
            return "N/A"
        return f"{val:.2f}{suffix}"
        
    def get_latest_valid(df, col_name):
        valid = df.dropna(subset=[col_name])
        if not valid.empty:
            return valid.iloc[0][col_name], valid.iloc[0]['year']
        return None, None

    roe, roe_yr = get_latest_valid(df_ratios_full, 'return_on_equity_pct')
    roce, roce_yr = get_latest_valid(df_ratios_full, 'return_on_capital_employed_pct')
    npm, npm_yr = get_latest_valid(df_ratios_full, 'net_profit_margin_pct')
    de, de_yr = get_latest_valid(df_ratios_full, 'debt_to_equity')
    rev_cagr, rev_yr = get_latest_valid(df_ratios_full, 'revenue_cagr_5yr')
    fcf, fcf_yr = get_latest_valid(df_ratios_full, 'free_cash_flow_cr')
        
    col1.metric("ROE", fmt(roe, "%"), help=f"Source year: {roe_yr}" if roe_yr else None)
    col2.metric("ROCE", fmt(roce, "%"), help=f"Source year: {roce_yr}" if roce_yr else None)
    col3.metric("Net Profit Margin", fmt(npm, "%"), help=f"Source year: {npm_yr}" if npm_yr else None)
    col4.metric("D/E", fmt(de, "x"), help=f"Source year: {de_yr}" if de_yr else None)
    col5.metric("Revenue CAGR 5yr", fmt(rev_cagr, "%"), help=f"Source year: {rev_yr}" if rev_yr else None)
    col6.metric("FCF (Latest)", fmt(fcf, " Cr"), help=f"Source year: {fcf_yr}" if fcf_yr else None)
else:
    st.info("No financial ratios data available for KPIs.")

st.divider()

# Charts
col_bar, col_line = st.columns(2)

with col_bar:
    st.subheader("Revenue vs Net Profit (10-Year)")
    df_pl = db.get_pl(company_id)
    if not df_pl.empty:
        df_pl_sorted = df_pl.sort_values(by='year', ascending=True)
        # We might have more than 10 years, limit to last 10
        df_pl_sorted = df_pl_sorted.tail(10)
        
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(x=df_pl_sorted['year'], y=df_pl_sorted['sales'], name='Revenue'))
        fig_bar.add_trace(go.Bar(x=df_pl_sorted['year'], y=df_pl_sorted['net_profit'], name='Net Profit'))
        fig_bar.update_layout(barmode='group', xaxis_title="Year", yaxis_title="Amount (Cr)")
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No P&L data available for this company.")

with col_line:
    st.subheader("ROE & ROCE Trend (10-Year)")
    if not df_ratios_full.empty:
        df_ratios_sorted = df_ratios_full.sort_values(by='year', ascending=True)
        df_ratios_sorted = df_ratios_sorted.tail(10)
        
        # Check if we have data to plot
        if 'return_on_equity_pct' in df_ratios_sorted.columns and 'return_on_capital_employed_pct' in df_ratios_sorted.columns:
            fig_line = go.Figure()
            fig_line.add_trace(go.Scatter(x=df_ratios_sorted['year'], y=df_ratios_sorted['return_on_equity_pct'], mode='lines+markers', name='ROE %'))
            fig_line.add_trace(go.Scatter(x=df_ratios_sorted['year'], y=df_ratios_sorted['return_on_capital_employed_pct'], mode='lines+markers', name='ROCE %'))
            fig_line.update_layout(xaxis_title="Year", yaxis_title="Percentage (%)")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
             st.info("ROE/ROCE data columns are missing.")
    else:
        st.info("No historical ratio data available for this company.")

st.divider()

# Pros and Cons
st.subheader("Pros & Cons")
df_pc = db.get_prosandcons(company_id)

if not df_pc.empty:
    pc_data = df_pc.iloc[0]
    pros_text = pc_data.get('pros')
    cons_text = pc_data.get('cons')
    
    col_pros, col_cons = st.columns(2)
    with col_pros:
        st.markdown("**Pros**")
        if pd.notna(pros_text) and pros_text:
            # Assuming bullet points or newlines, we'll split by newline for safety
            for item in pros_text.split('\n'):
                if item.strip():
                    st.markdown(f"✅ {item.strip()}")
        else:
            st.write("No pros listed.")
            
    with col_cons:
        st.markdown("**Cons**")
        if pd.notna(cons_text) and cons_text:
            for item in cons_text.split('\n'):
                if item.strip():
                    st.markdown(f"❌ {item.strip()}")
        else:
            st.write("No cons listed.")
else:
    st.info("No qualitative data available for this company.")
