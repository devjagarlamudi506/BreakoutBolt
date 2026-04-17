import sqlite3
conn = sqlite3.connect("breakoutbolt.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT symbol, entry, stop_loss, target, status, opened_at, closed_at FROM positions ORDER BY status, symbol"
).fetchall()
print(f"{'Symbol':<7} {'Entry':>8} {'Stop':>8} {'Target':>8} {'Status':<16} {'Opened':<26} {'Closed'}")
print("-" * 110)
for r in rows:
    print(f"{r['symbol']:<7} {r['entry']:>8.2f} {r['stop_loss']:>8.2f} {r['target']:>8.2f} {r['status']:<16} {r['opened_at'] or '':<26} {r['closed_at'] or ''}")
conn.close()
