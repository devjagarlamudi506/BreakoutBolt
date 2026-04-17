"""Analyze today's bot activity from the database."""
import sqlite3
from datetime import date

TODAY = str(date.today())
conn = sqlite3.connect("breakoutbolt.db")
conn.row_factory = sqlite3.Row

# Scan snapshots
scans = conn.execute(
    "SELECT COUNT(*) as cnt FROM scan_snapshots WHERE trading_date=?", (TODAY,)
).fetchone()
print(f"=== SCAN SNAPSHOTS: {scans['cnt']} rows ===\n")

# Signals breakdown
sigs = conn.execute(
    "SELECT side, COUNT(*) as cnt FROM signals WHERE trading_date=? GROUP BY side",
    (TODAY,),
).fetchall()
print("=== SIGNALS ===")
for s in sigs:
    print(f"  {s['side']}: {s['cnt']}")
print()

# Orders
orders = conn.execute(
    "SELECT COUNT(*) as cnt FROM orders WHERE trading_date=?", (TODAY,)
).fetchone()
print(f"=== ORDERS: {orders['cnt']} ===\n")

# Positions
positions = conn.execute("SELECT * FROM positions").fetchall()
print(f"=== ACTIVE POSITIONS: {len(positions)} ===")
for p in positions:
    d = dict(p)
    print(f"  {d['symbol']:6s} | side={d.get('side','?')} | qty={d.get('qty','?')} | "
          f"entry={d.get('entry','?')} | stop={d.get('stop_loss','?')} | target={d.get('target','?')} | "
          f"status={d.get('status','?')} | pattern={d.get('pattern','?')}")
print()

# Unique symbols scanned
syms = conn.execute(
    "SELECT DISTINCT symbol FROM scan_snapshots WHERE trading_date=?", (TODAY,)
).fetchall()
print(f"=== UNIQUE SYMBOLS SCANNED: {len(syms)} ===")
print(f"  {', '.join(s['symbol'] for s in syms)}\n")

# BUY signals detail
buys = conn.execute(
    "SELECT symbol, reason, ts, pattern, confidence, ai_approved, ai_note FROM signals WHERE trading_date=? AND side='BUY' ORDER BY ts",
    (TODAY,),
).fetchall()
print(f"=== BUY SIGNALS: {len(buys)} ===")
for b in buys:
    print(f"  {b['ts']} | {b['symbol']:6s} | {b['pattern']:12s} | conf={b['confidence']} | ai={b['ai_approved']} | {b['reason']}")
    if b['ai_note']:
        print(f"{'':21s}ai_note: {b['ai_note']}")
print()

# HOLD signals - top rejection reasons
holds = conn.execute(
    """SELECT symbol, reason, COUNT(*) as cnt
       FROM signals WHERE trading_date=? AND side='HOLD'
       GROUP BY symbol ORDER BY cnt DESC LIMIT 10""",
    (TODAY,),
).fetchall()
print(f"=== TOP HOLD SYMBOLS (most rejected) ===")
for h in holds:
    print(f"  {h['symbol']:6s} ({h['cnt']}x) | {h['reason'][:120]}")

# Orders detail
print()
ords = conn.execute(
    "SELECT symbol, side, qty, order_type, status, submitted_at, broker_order_id FROM orders WHERE trading_date=? ORDER BY submitted_at",
    (TODAY,),
).fetchall()
print(f"=== ORDER DETAILS: {len(ords)} ===")
for o in ords:
    print(f"  {o['submitted_at']} | {o['symbol']:6s} | {o['side']} | qty={o['qty']} | type={o['order_type']} | status={o['status']}")
print()

# Scan cycles
cycles = conn.execute(
    """SELECT substr(ts,1,19) as cycle_ts, COUNT(*) as cnt
       FROM scan_snapshots WHERE trading_date=?
       GROUP BY cycle_ts ORDER BY cycle_ts""",
    (TODAY,),
).fetchall()
print(f"=== SCAN CYCLES: {len(cycles)} ===")
for c in cycles:
    print(f"  {c['cycle_ts']} -> {c['cnt']} symbols")
print()

# Watchlist
wl = conn.execute("SELECT symbol, score FROM watchlist ORDER BY score DESC").fetchall()
print(f"=== CURRENT WATCHLIST: {len(wl)} symbols ===")
for w in wl[:10]:
    print(f"  {w['symbol']:6s} score={w['score']:.4f}")
if len(wl) > 10:
    print(f"  ... and {len(wl)-10} more")

conn.close()
