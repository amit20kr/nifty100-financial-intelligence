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
from src.dashboard.utils import db
from src.screener.presets import PRESETS

st.set_page_config(page_title="Screener - Nifty 100 Analytics", layout="wide")
st.title("Screener")

engine = db.get_engine()
if not engine:
    st.error("Engine failed to load.")
    st.stop()

# State management
if "preset_active" not in st.session_state:
    st.session_state.preset_active = "Custom"


def set_preset(name):
    st.session_state.preset_active = name


def clear_preset():
    st.session_state.preset_active = "Custom"


# Layout
st.sidebar.header("Presets")
for preset in PRESETS.keys():
    st.sidebar.button(
        preset, on_click=set_preset, args=(preset,), use_container_width=True
    )

st.sidebar.divider()
st.sidebar.header("Custom Filters")
st.sidebar.caption("Modifying any slider switches to Custom mode.")

# Sliders
criteria_dict = {}


def create_slider(label, key, metric, min_v, max_v, default, step=1.0):
    val = st.sidebar.slider(
        label, min_v, max_v, default, step=step, key=key, on_change=clear_preset
    )
    criteria_dict[metric] = val


create_slider("Min ROE (%)", "roe", "return_on_equity_pct", -20.0, 50.0, 15.0)
create_slider("Max D/E (x)", "de", "debt_to_equity", 0.0, 5.0, 1.0, 0.1)
create_slider("Min FCF (Cr)", "fcf", "free_cash_flow_cr", -5000.0, 50000.0, 0.0, 500.0)
create_slider("Min Rev CAGR (%)", "rev_cagr", "revenue_cagr_5yr", -10.0, 30.0, 10.0)
create_slider("Min PAT CAGR (%)", "pat_cagr", "pat_cagr_5yr", -10.0, 30.0, 10.0)
create_slider("Min OPM (%)", "opm", "operating_profit_margin_pct", -10.0, 50.0, 10.0)
create_slider("Max P/E (x)", "pe", "pe_ratio", 5.0, 150.0, 50.0)
create_slider("Max P/B (x)", "pb", "pb_ratio", 0.5, 30.0, 10.0, 0.5)
create_slider("Min Div Yield (%)", "div", "dividend_yield_pct", 0.0, 10.0, 0.0, 0.1)
create_slider("Min ICR (x)", "icr", "interest_coverage", -5.0, 50.0, 3.0, 0.5)

if st.session_state.preset_active != "Custom":
    st.subheader(f"Preset: {st.session_state.preset_active}")
    preset_func = PRESETS[st.session_state.preset_active]
    df_result = preset_func(engine)
else:
    st.subheader("Custom Screener")
    try:
        df_result = engine.apply(criteria_dict)
    except Exception as e:
        st.error(f"Error applying filters: {e}")
        df_result = pd.DataFrame()

if not df_result.empty:
    st.caption(f"**{len(df_result)}** companies match your filters")

    companies_df = db.get_companies()

    display_df = df_result.copy()
    if "company_name" not in display_df.columns:
        display_df = display_df.merge(
            companies_df[["id", "company_name"]],
            left_on="company_id",
            right_on="id",
            how="left",
        )

    front_cols = ["company_name", "broad_sector", "screener_composite_score"]

    metric_cols = [
        "return_on_equity_pct",
        "debt_to_equity",
        "free_cash_flow_cr",
        "revenue_cagr_5yr",
        "pat_cagr_5yr",
        "operating_profit_margin_pct",
        "pe_ratio",
        "pb_ratio",
        "dividend_yield_pct",
        "interest_coverage",
    ]

    display_cols = front_cols + [c for c in metric_cols if c in display_df.columns]

    # Fallback if some presets drop standard metric columns
    display_cols = [c for c in display_cols if c in display_df.columns]

    # Sort by screener_composite_score descending
    if "screener_composite_score" in display_df.columns:
        display_df = display_df.sort_values(
            by="screener_composite_score", ascending=False
        )

    st.dataframe(display_df[display_cols], hide_index=True, use_container_width=True)

    csv = display_df.to_csv(index=False)
    st.download_button(
        label="Download Results as CSV",
        data=csv,
        file_name="screener_results.csv",
        mime="text/csv",
    )
else:
    st.warning("No companies match the current filter criteria.")
