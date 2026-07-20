import sqlite3
import pandas as pd

conn = sqlite3.connect("db/nifty100.db")
tables = [
    r[0]
    for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
]
print("=== TABLE ROW COUNTS ===")
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t:25s}: {count:>6} rows")
print(f"\nTotal tables: {len(tables)}")
print("Tables:", tables)

print("\n=== FK INTEGRITY CHECK ===")
fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
print(f"FK violations: {len(fk_rows)}")

print("\n=== LOAD AUDIT ===")
try:
    df = pd.read_csv("output/load_audit.csv")
    print(
        df[
            ["table", "rows_in", "rows_out", "db_rows", "db_fk_ok", "status"]
        ].to_string()
    )
except Exception as e:
    print(f"Error: {e}")

print("\n=== VALIDATION FAILURES SUMMARY ===")
try:
    vf = pd.read_csv("output/validation_failures.csv")
    print("By rule_id:")
    print(
        vf.groupby(["rule_id", "severity"]).size().reset_index(name="count").to_string()
    )
    print(f"\nTotal failures: {len(vf)}")
    print(f"CRITICAL: {(vf.severity=='CRITICAL').sum()}")
    print(f"WARNING: {(vf.severity=='WARNING').sum()}")
except Exception as e:
    print(f"Error: {e}")
