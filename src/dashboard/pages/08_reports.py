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
from src.dashboard.utils import db

st.set_page_config(page_title="Annual Reports - Nifty 100 Analytics", layout="wide")
st.title("Qualitative Reports & Insights")

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

company_data = df_companies[df_companies["id"] == company_id].iloc[0]
st.subheader(f"Research: {id_to_name[company_id]}")

# NSE Link
nse_profile = company_data.get("nse_profile")
if pd.notna(nse_profile) and nse_profile:
    st.link_button(
        "View Full NSE Profile & Annual Reports", url=nse_profile, type="primary"
    )
else:
    st.info("NSE Profile link not available.")

st.divider()

# Pros & Cons
df_pc = db.get_prosandcons(company_id)

if not df_pc.empty:
    pc_data = df_pc.iloc[0]
    pros_text = pc_data.get("pros")
    cons_text = pc_data.get("cons")

    col_pros, col_cons = st.columns(2)
    with col_pros:
        st.markdown("### 👍 Pros")
        if pd.notna(pros_text) and pros_text:
            for item in pros_text.split("\n"):
                if item.strip():
                    st.markdown(f"- {item.strip()}")
        else:
            st.write("No pros listed.")

    with col_cons:
        st.markdown("### 👎 Cons")
        if pd.notna(cons_text) and cons_text:
            for item in cons_text.split("\n"):
                if item.strip():
                    st.markdown(f"- {item.strip()}")
        else:
            st.write("No cons listed.")
else:
    st.info("No qualitative pros/cons data available for this company.")
