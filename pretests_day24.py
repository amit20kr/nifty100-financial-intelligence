import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv
from src.screener.engine import FilterEngine
from src.screener.presets import PRESETS

load_dotenv()
db_path = os.getenv('DB_PATH', 'db/nifty100.db')
config_path = os.getenv('SCREENER_CONFIG', 'config/screener_config.yaml')

print('=== PRETEST 1: FilterEngine Engine & Composite Score ===')
engine = FilterEngine(db_path, config_path)
print('Total rows in engine.df:', len(engine.df))
print('screener_composite_score null count:', engine.df['screener_composite_score'].isna().sum())

print('\n=== PRETEST 2: Presets Evaluation ===')
for preset_name, preset_func in PRESETS.items():
    df_preset = preset_func(engine)
    print(f"Preset '{preset_name}': {len(df_preset)} rows")

conn = sqlite3.connect(db_path)

print('\n=== PRETEST 3: Peer Percentiles Metrics ===')
metrics_df = pd.read_sql_query('SELECT DISTINCT metric FROM peer_percentiles ORDER BY metric', conn)
print(metrics_df['metric'].tolist())

print('\n=== PRETEST 4: Peer Benchmark Counts ===')
benchmarks_df = pd.read_sql_query('SELECT peer_group_name, COUNT(*) as c FROM peer_groups WHERE is_benchmark=1 GROUP BY peer_group_name', conn)
print(benchmarks_df)

conn.close()

print('\n=== PRETEST 5: Peer Group Warnings ===')
warnings_path = 'output/peer_group_warnings.csv'
if os.path.exists(warnings_path):
    warnings_df = pd.read_csv(warnings_path)
    print(warnings_df)
else:
    print('output/peer_group_warnings.csv not found.')

