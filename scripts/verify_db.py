import sqlite3

conn = sqlite3.connect("db/nifty100.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== DB ROW COUNTS ===")
for (t,) in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:30s} {cnt:>6} rows")

print("\n=== FK CHECK ===")
fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
print(f"  FK violations: {len(fk_violations)}")

conn.close()
