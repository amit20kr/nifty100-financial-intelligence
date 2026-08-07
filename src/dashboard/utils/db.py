import os
import sqlite3
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from src.screener.engine import FilterEngine

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")


def _get_connection():
    # Helper to avoid repetitive connection code, but each cached function calls this inside.
    return sqlite3.connect(DB_PATH)


@st.cache_data(ttl=600)
def get_companies():
    """Fetch all companies."""
    try:
        with _get_connection() as conn:
            query = "SELECT * FROM companies"
            df = pd.read_sql_query(query, conn)
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_ratios(company_id: str, year: str = None):
    """
    Fetch financial ratios.
    If year=None, returns full multi-year time series.
    If year is specified, returns single-row filter.
    """
    try:
        with _get_connection() as conn:
            if year:
                query = (
                    "SELECT * FROM financial_ratios WHERE company_id = ? AND year = ?"
                )
                params = (company_id, year)
            else:
                query = "SELECT * FROM financial_ratios WHERE company_id = ? ORDER BY year DESC"
                params = (company_id,)
            df = pd.read_sql_query(query, conn, params=params)
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_pl(company_id: str):
    """Fetch P&L statements for a company."""
    try:
        with _get_connection() as conn:
            query = (
                "SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year DESC"
            )
            df = pd.read_sql_query(query, conn, params=(company_id,))
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_bs(company_id: str):
    """Fetch Balance Sheets for a company."""
    try:
        with _get_connection() as conn:
            query = "SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year DESC"
            df = pd.read_sql_query(query, conn, params=(company_id,))
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_cf(company_id: str):
    """Fetch Cashflow statements for a company."""
    try:
        with _get_connection() as conn:
            query = "SELECT * FROM cashflow WHERE company_id = ? ORDER BY year DESC"
            df = pd.read_sql_query(query, conn, params=(company_id,))
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_sectors():
    """Fetch sector breakdown."""
    try:
        with _get_connection() as conn:
            query = "SELECT * FROM sectors"
            df = pd.read_sql_query(query, conn)
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_peers(group_name: str):
    """Fetch peer group and their percentiles."""
    try:
        with _get_connection() as conn:
            query = "SELECT * FROM peer_groups WHERE peer_group_name = ?"
            df = pd.read_sql_query(query, conn, params=(group_name,))
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_valuation(company_id: str = None):
    """
    Fetch valuation metrics for a company from the generated summary.
    If company_id is None, returns the entire universe.
    """
    try:
        val_path = os.getenv("VALUATION_SUMMARY_PATH", "output/valuation_summary.xlsx")
        if not os.path.exists(val_path):
            return pd.DataFrame()

        df = pd.read_excel(val_path)

        if company_id:
            df = df[df["company_id"] == company_id]

        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_universe_ratios(year: str = None):
    """
    Fetch financial ratios for all companies.
    If year is specified, filters by that year.
    """
    try:
        with _get_connection() as conn:
            if year:
                query = "SELECT * FROM financial_ratios WHERE year = ?"
                params = (year,)
            else:
                query = "SELECT * FROM financial_ratios"
                params = ()
            df = pd.read_sql_query(query, conn, params=params)
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_universe_market_cap(year: str = None):
    """
    Fetch market cap metrics for all companies.
    If year is specified, filters by that year.
    """
    try:
        with _get_connection() as conn:
            if year:
                query = "SELECT * FROM market_cap WHERE year = ?"
                params = (year,)
            else:
                query = "SELECT * FROM market_cap"
                params = ()
            df = pd.read_sql_query(query, conn, params=params)
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600)
def get_prosandcons(company_id: str):
    """Fetch pros and cons for a given company."""
    try:
        with _get_connection() as conn:
            query = "SELECT * FROM prosandcons WHERE company_id = ?"
            df = pd.read_sql_query(query, conn, params=(company_id,))
            return df
    except Exception:
        return pd.DataFrame()


@st.cache_resource
def get_engine():
    """Cache the FilterEngine instance for preset usage."""
    try:
        config_path = os.getenv("SCREENER_CONFIG", "config/screener_config.yaml")
        return FilterEngine(DB_PATH, config_path)
    except Exception as e:
        st.error(f"Error loading FilterEngine: {e}")
        return None


@st.cache_data(ttl=600)
def get_screener_data():
    """
    Return the full pre-joined DataFrame from engine.
    """
    engine = get_engine()
    if engine:
        return engine.df.copy()
    return pd.DataFrame()


@st.cache_data(ttl=600)
def get_peer_groups():
    """Fetch distinct list of peer groups."""
    try:
        with _get_connection() as conn:
            query = "SELECT DISTINCT peer_group_name FROM peer_groups ORDER BY peer_group_name"
            df = pd.read_sql_query(query, conn)
            return df["peer_group_name"].tolist()
    except Exception:
        return []


@st.cache_data(ttl=600)
def get_peer_percentiles(group_name: str):
    """Fetch percentile ranks and raw values for a peer group."""
    try:
        with _get_connection() as conn:
            query = """
            SELECT p.company_id, p.metric, p.value, p.percentile_rank, p.year, p.year_mismatch_flag,
                   g.is_benchmark, c.company_name
            FROM peer_percentiles p
            JOIN peer_groups g ON p.company_id = g.company_id AND p.peer_group_name = g.peer_group_name
            JOIN companies c ON p.company_id = c.id
            WHERE p.peer_group_name = ?
            """
            df = pd.read_sql_query(query, conn, params=(group_name,))
            return df
    except Exception:
        return pd.DataFrame()
