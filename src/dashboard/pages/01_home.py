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
from src.dashboard.utils import db

st.set_page_config(page_title="Home - Nifty 100 Analytics", layout="wide")
st.title("Home")

# Fetch full universe to extract distinct years
df_all_ratios = db.get_universe_ratios()
if df_all_ratios.empty:
    st.warning("No financial ratios data found in the database.")
    st.stop()

available_years = sorted(df_all_ratios['year'].dropna().unique(), reverse=True)

# Sidebar Year Selector
selected_year = st.sidebar.selectbox("Select Year", options=available_years)

# Fetch data for selected year
df_ratios = db.get_universe_ratios(selected_year)
df_mcap = db.get_universe_market_cap(selected_year)
df_companies = db.get_companies()
df_sectors = db.get_sectors()

# KPIs Calculation
if not df_ratios.empty:
    avg_roe = df_ratios['return_on_equity_pct'].mean()
    med_rev_cagr = df_ratios['revenue_cagr_5yr'].median()
    debt_free = df_ratios['icr_at_risk_flag'].isna().sum()
    
    # Exclude Financials for Median D/E
    if not df_sectors.empty:
        df_ratios_sectors = df_ratios.merge(df_sectors, on='company_id', how='left')
        non_fin_ratios = df_ratios_sectors[df_ratios_sectors['broad_sector'] != 'Financials']
        med_de = non_fin_ratios['debt_to_equity'].median()
    else:
        med_de = df_ratios['debt_to_equity'].median()
else:
    avg_roe = pd.NA
    med_rev_cagr = pd.NA
    debt_free = pd.NA
    med_de = pd.NA

# Median P/E Calculation (exclude <= 0 and NULL)
if not df_mcap.empty:
    valid_pe = df_mcap[(df_mcap['pe_ratio'].notna()) & (df_mcap['pe_ratio'] > 0)]
    med_pe = valid_pe['pe_ratio'].median()
else:
    med_pe = pd.NA

total_companies = len(df_companies) if not df_companies.empty else pd.NA

# Render KPIs
st.subheader(f"Universe Summary ({selected_year})")
col1, col2, col3, col4, col5, col6 = st.columns(6)

def fmt(val, suffix=""):
    if pd.isna(val):
        return "No data"
    if isinstance(val, (int, float)):
        return f"{val:.2f}{suffix}" if isinstance(val, float) else f"{val}{suffix}"
    return val

col1.metric("Average ROE", fmt(avg_roe, "%"))
col2.metric("Median P/E", fmt(med_pe))
col3.metric("Median D/E (ex-Fin)", fmt(med_de))
col4.metric("Total Companies", fmt(total_companies))
col5.metric("Median Rev CAGR 5yr", fmt(med_rev_cagr, "%"))
col6.metric("Debt-Free Companies", fmt(debt_free))

st.divider()

# Charts and Tables
col_chart, col_table = st.columns([1, 1])

with col_chart:
    st.subheader("Sector Breakdown")
    if not df_sectors.empty:
        sector_counts = df_sectors['broad_sector'].value_counts().reset_index()
        sector_counts.columns = ['Sector', 'Count']
        fig = px.pie(sector_counts, values='Count', names='Sector', hole=0.4, title="Companies per Sector")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No sector data available.")

with col_table:
    st.subheader("Top 5 Companies by Screener Score")
    st.caption("As of latest available fiscal year")
    
    df_scores = db.get_screener_data()
    if not df_scores.empty and not df_companies.empty and not df_sectors.empty:
        # Merge to get names and sectors
        top5 = df_scores.merge(df_companies[['id', 'company_name']], left_on='company_id', right_on='id', how='left')
        
        # We don't need to merge df_sectors because get_screener_data already has broad_sector!
        # But we can just use the broad_sector from engine.df if available, else merge.
        if 'broad_sector' not in top5.columns:
            top5 = top5.merge(df_sectors[['company_id', 'broad_sector']], on='company_id', how='left')
        
        # Sort and take top 5
        top5 = top5.sort_values(by='screener_composite_score', ascending=False).head(5)
        top5 = top5[['company_name', 'broad_sector', 'screener_composite_score']]
        top5.columns = ['Company', 'Sector', 'Score']
        top5['Score'] = top5['Score'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        
        st.dataframe(top5, hide_index=True, use_container_width=True)
    else:
        st.info("Screener score data is currently unavailable.")
