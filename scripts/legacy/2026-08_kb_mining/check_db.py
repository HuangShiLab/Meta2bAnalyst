import sqlite3
c = sqlite3.connect('meta2banalyst.db')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)
for t in tables:
    cnt = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f'  {t}: {cnt} rows')
c.close()
