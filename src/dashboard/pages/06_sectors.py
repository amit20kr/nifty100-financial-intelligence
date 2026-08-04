# ── permanent path fix (must be first) ──────────────────────────────────────
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

st.set_page_config(page_title="Sector Analysis - Nifty 100 Analytics", layout="wide")
st.title("Sector Analysis")

df_screener = db.get_screener_data()
df_companies = db.get_companies()

if df_screener.empty:
    st.warning("No screener data available.")
    st.stop()

# Merge company_name
if not df_companies.empty:
    df_screener = df_screener.merge(df_companies[['id', 'company_name']], left_on='company_id', right_on='id', how='left')
    df_screener['company_name'] = df_screener['company_name'].fillna(df_screener['company_id'])
else:
    df_screener['company_name'] = df_screener['company_id']

# Ensure we have required columns, if not fail gracefully
if 'broad_sector' not in df_screener.columns:
    st.warning("Sector data is missing from the database view.")
    st.stop()

sectors = sorted(df_screener['broad_sector'].dropna().unique().tolist())
sectors.insert(0, "All Sectors")

selected_sector = st.selectbox("Select Sector", options=sectors)

if selected_sector != "All Sectors":
    df_filtered = df_screener[df_screener['broad_sector'] == selected_sector]
else:
    df_filtered = df_screener.copy()

if df_filtered.empty:
    st.info("No companies found in this sector.")
    st.stop()

st.divider()

# Sector Metrics
if selected_sector != "All Sectors":
    st.subheader(f"Metrics for {selected_sector}")
    # Group by broad sector, taking median. Using as_index=False handles single-company sectors gracefully
    sector_medians = df_filtered.groupby('broad_sector', as_index=False).median(numeric_only=True)
    
    if not sector_medians.empty:
        sm = sector_medians.iloc[0]
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Companies", len(df_filtered))
        col2.metric("Median ROE", f"{sm.get('return_on_equity_pct', pd.NA):.2f}%" if pd.notna(sm.get('return_on_equity_pct')) else "N/A")
        col3.metric("Median P/E", f"{sm.get('pe_ratio', pd.NA):.2f}x" if pd.notna(sm.get('pe_ratio')) else "N/A")
        col4.metric("Median D/E", f"{sm.get('debt_to_equity', pd.NA):.2f}x" if pd.notna(sm.get('debt_to_equity')) else "N/A")

st.divider()

col_tree, col_bar = st.columns(2)

with col_tree:
    st.subheader("Market Capitalization Map")
    # Edge case: drop 0/NULL market cap to prevent Plotly errors
    df_tree = df_filtered.copy()
    if 'market_cap_crore' in df_tree.columns:
        df_tree = df_tree[df_tree['market_cap_crore'] > 0].dropna(subset=['market_cap_crore'])
        
        if not df_tree.empty:
            fig_tree = px.treemap(
                df_tree,
                path=['broad_sector', 'company_name'],
                values='market_cap_crore',
                color='return_on_equity_pct',
                color_continuous_scale='RdYlGn',
                title="Sized by Market Cap, Colored by ROE"
            )
            fig_tree.update_layout(margin=dict(t=50, l=25, r=25, b=25))
            st.plotly_chart(fig_tree, use_container_width=True)
        else:
            st.info("No valid market cap data available to render treemap.")
    else:
        st.info("Market cap data not found.")

with col_bar:
    st.subheader("Composite Score Ranking")
    if 'screener_composite_score' in df_filtered.columns:
        df_rank = df_filtered.sort_values('screener_composite_score', ascending=True).dropna(subset=['screener_composite_score'])
        if not df_rank.empty:
            fig_bar = px.bar(
                df_rank,
                x='screener_composite_score',
                y='company_name',
                orientation='h',
                title="Overall Screener Score"
            )
            fig_bar.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Composite scores not generated for these companies.")
    else:
        st.info("Composite score data not found.")
