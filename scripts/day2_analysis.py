"""Full Day 2 analysis."""
import sqlite3
from datetime import date

TODAY = str(date.today())
conn = sqlite3.connect("breakoutbolt.db")
conn.row_factory = sqlite3.Row

print("=" * 70)
print(f"  BREAKOUTBOLT DAY 2 ANALYSIS — {TODAY}")
print("=" * 70)

# Positions summary
positions = conn.execute("SELECT * FROM positions").fetchall()
print(f"\n{'='*70}")
print("  POSITIONS SUMMARY")
print(f"{'='*70}")

total_entries = len(positions)
targets_hit = [p for p in positions if p['status'] == 'TARGET_HIT']
stops_hit = [p for p in positions if p['status'] == 'STOP_LOSS_HIT']
eod_closed = [p for p in positions if p['status'] == 'EOD_CLOSED']

print(f"  Total entries:    {total_entries}")
print(f"  Target hit:       {len(targets_hit)}")
print(f"  Stop loss hit:    {len(stops_hit)}")
print(f"  EOD closed:       {len(eod_closed)}")
print(f"  Win rate:         {len(targets_hit)}/{len(targets_hit)+len(stops_hit)} = {len(targets_hit)/(len(targets_hit)+len(stops_hit))*100:.0f}% (resolved trades)")

print(f"\n  {'Symbol':<7} {'Entry':>8} {'Stop':>8} {'Target':>8} {'Status':<16} {'Risk$':>7} {'Reward$':>8}")
print(f"  {'-'*64}")
for p in positions:
    risk = (p['entry'] - p['stop_loss']) * p['qty']
    reward = (p['target'] - p['entry']) * p['qty']
    print(f"  {p['symbol']:<7} {p['entry']:>8.2f} {p['stop_loss']:>8.2f} {p['target']:>8.2f} {p['status']:<16} ${risk:>6.0f} ${reward:>7.0f}")

# Scan stats
print(f"\n{'='*70}")
print("  SCAN STATISTICS")
print(f"{'='*70}")

scans = conn.execute("SELECT COUNT(*) as cnt FROM scan_snapshots WHERE trading_date=?", (TODAY,)).fetchone()
sigs = conn.execute("SELECT side, COUNT(*) as cnt FROM signals WHERE trading_date=? GROUP BY side", (TODAY,)).fetchall()
orders = conn.execute("SELECT COUNT(*) as cnt FROM orders WHERE trading_date=?", (TODAY,)).fetchone()

print(f"  Scan snapshots:   {scans['cnt']}")
for s in sigs:
    print(f"  {s['side']} signals:    {s['cnt']}")
print(f"  Orders placed:    {orders['cnt']}")

# Unique BUY symbols
buy_syms = conn.execute(
    "SELECT DISTINCT symbol FROM signals WHERE trading_date=? AND side='BUY'", (TODAY,)
).fetchall()
print(f"  Unique BUY tickers: {len(buy_syms)} — {', '.join(s['symbol'] for s in buy_syms)}")

# Scan cycles
cycles = conn.execute(
    """SELECT substr(ts,1,16) as cycle_ts, COUNT(*) as cnt
       FROM scan_snapshots WHERE trading_date=?
       GROUP BY cycle_ts ORDER BY cycle_ts""",
    (TODAY,),
).fetchall()
print(f"  Scan cycles:      {len(cycles)}")
if cycles:
    print(f"  First scan:       {cycles[0]['cycle_ts']} UTC")
    print(f"  Last scan:        {cycles[-1]['cycle_ts']} UTC")

# API usage from signals - rejection reasons breakdown
print(f"\n{'='*70}")
print("  REJECTION ANALYSIS (HOLD signals)")
print(f"{'='*70}")

# Parse out rejection reasons
reasons = conn.execute(
    """SELECT reason, COUNT(*) as cnt
       FROM signals WHERE trading_date=? AND side='HOLD'
       GROUP BY reason ORDER BY cnt DESC LIMIT 15""",
    (TODAY,),
).fetchall()
for r in reasons:
    short = r['reason'][:90]
    print(f"  {r['cnt']:>4}x  {short}")

# BUY signals blocked
print(f"\n{'='*70}")
print("  BLOCKED BUY SIGNALS (AI-approved but position limit)")
print(f"{'='*70}")

blocked = conn.execute(
    """SELECT symbol, COUNT(*) as cnt, pattern, MIN(ts) as first, MAX(ts) as last
       FROM signals WHERE trading_date=? AND side='BUY' AND ai_approved=0
       GROUP BY symbol ORDER BY cnt DESC""",
    (TODAY,),
).fetchall()
for b in blocked:
    print(f"  {b['symbol']:<7} {b['cnt']:>3}x blocked | {b['pattern']:<25} | {b['first'][:16]}..{b['last'][:16]}")

# Executed BUY signals
print(f"\n{'='*70}")
print("  EXECUTED BUY SIGNALS")
print(f"{'='*70}")

executed = conn.execute(
    """SELECT symbol, pattern, confidence, ts, ai_note
       FROM signals WHERE trading_date=? AND side='BUY' AND ai_approved=1
       ORDER BY ts""",
    (TODAY,),
).fetchall()
for e in executed:
    print(f"  {e['ts'][:19]} | {e['symbol']:<7} | {e['pattern']:<25} | conf={e['confidence']:.3f}")

conn.close()
