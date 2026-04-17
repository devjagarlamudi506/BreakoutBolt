"""Quick DB review script for evening evaluation."""
import sqlite3

conn = sqlite3.connect("breakoutbolt.db")
c = conn.cursor()

# Show schemas
print("=== TABLE SCHEMAS ===")
for row in c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"):
    print(row[0][:200])
    print()

# Table row counts
print("=== ROW COUNTS ===")
for tbl in ["watchlist", "scan_snapshots", "signals", "positions", "orders"]:
    try:
        c.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"  {tbl}: {c.fetchone()[0]}")
    except Exception as e:
        print(f"  {tbl}: {e}")

# Signals
print("\n=== SIGNALS ===")
c.execute("SELECT COUNT(*) FROM signals")
total = c.fetchone()[0]
print(f"Total: {total}")
if total > 0:
    # Get column names
    c.execute("PRAGMA table_info(signals)")
    cols = [r[1] for r in c.fetchall()]
    print(f"Columns: {cols}")

    # Side distribution
    print("\nSide distribution:")
    c.execute("SELECT side, COUNT(*) FROM signals GROUP BY side")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1]}")

    # Non-HOLD signals
    print("\nNon-HOLD signals:")
    c.execute("SELECT * FROM signals WHERE side != 'HOLD' ORDER BY timestamp")
    rows = c.fetchall()
    if rows:
        for row in rows:
            print(f"  {row}")
    else:
        print("  None")

    # Top reasons
    print("\nTop rejection reasons:")
    c.execute("SELECT reason, COUNT(*) as cnt FROM signals GROUP BY reason ORDER BY cnt DESC LIMIT 15")
    for row in c.fetchall():
        print(f"  {row[1]:4d}x  {row[0][:120]}")

    # Hour distribution
    print("\nSignals by hour:")
    c.execute("SELECT substr(timestamp, 12, 2) as hour, COUNT(*) FROM signals GROUP BY hour ORDER BY hour")
    for row in c.fetchall():
        print(f"  Hour {row[0]}: {row[1]}")

# Orders
print("\n=== ORDERS ===")
c.execute("SELECT COUNT(*) FROM orders")
cnt = c.fetchone()[0]
print(f"Total: {cnt}")
if cnt > 0:
    c.execute("SELECT * FROM orders")
    for row in c.fetchall():
        print(f"  {row}")

# Positions
print("\n=== POSITIONS ===")
c.execute("SELECT COUNT(*) FROM positions")
cnt = c.fetchone()[0]
print(f"Total: {cnt}")
if cnt > 0:
    c.execute("SELECT * FROM positions")
    for row in c.fetchall():
        print(f"  {row}")

# Snapshots
print("\n=== RECENT SNAPSHOTS (last 10) ===")
c.execute("PRAGMA table_info(scan_snapshots)")
snap_cols = [r[1] for r in c.fetchall()]
print(f"Columns: {snap_cols}")
c.execute("SELECT * FROM scan_snapshots ORDER BY timestamp DESC LIMIT 10")
for row in c.fetchall():
    print(f"  {row}")

# Watchlist
print("\n=== CURRENT WATCHLIST ===")
c.execute("SELECT * FROM watchlist")
wl = c.fetchall()
print(f"Symbols: {[r[0] if len(r)==1 else r for r in wl]}")

conn.close()
