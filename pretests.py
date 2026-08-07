import sqlite3
import pandas as pd
from src.screener.engine import FilterEngine
from dotenv import load_dotenv
import os

load_dotenv()
db_path = os.getenv("DB_PATH", "db/nifty100.db")
conn = sqlite3.connect(db_path)

print("--- DISTINCT YEARS ---")
years = pd.read_sql_query(
    "SELECT DISTINCT year FROM financial_ratios ORDER BY year", conn
)
print(years["year"].tolist())

print("\n--- NSE PROFILES (LIMIT 5) ---")
nse_profiles = pd.read_sql_query(
    "SELECT id, company_name, nse_profile FROM companies LIMIT 5", conn
)
print(nse_profiles)
null_nse = pd.read_sql_query(
    'SELECT COUNT(*) as c FROM companies WHERE nse_profile IS NULL OR nse_profile = ""',
    conn,
)
print("NULL/Empty nse_profile count:", null_nse["c"][0])

print("\n--- PROS AND CONS COUNT ---")
pc_count = pd.read_sql_query("SELECT COUNT(*) as c FROM prosandcons", conn)
print(pc_count["c"][0], "/ 92")

print("\n--- FILTER ENGINE COLUMNS ---")
engine = FilterEngine(db_path)
print(
    "composite_quality_score in columns:",
    "composite_quality_score" in engine.df.columns,
)
print(
    "screener_composite_score in columns:",
    "screener_composite_score" in engine.df.columns,
)

print("\n--- PE RATIO CHECK ---")
fr_cols = pd.read_sql_query("PRAGMA table_info(financial_ratios)", conn)
print("pe_ratio in financial_ratios:", "pe_ratio" in fr_cols["name"].tolist())

conn.close()
