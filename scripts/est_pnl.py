import sqlite3
conn = sqlite3.connect("breakoutbolt.db")
conn.row_factory = sqlite3.Row

print("=" * 70)
print("  ESTIMATED P&L (Day 2)")
print("=" * 70)

total_pnl = 0

# EOD closed positions - use last scan price as proxy
symbols = ["AMD", "AVGO", "HIMS", "INTC", "MSTR", "RKLB"]
for sym in symbols:
    row = conn.execute("SELECT last_price, ts FROM scan_snapshots WHERE symbol=? ORDER BY ts DESC LIMIT 1", (sym,)).fetchone()
    pos = conn.execute("SELECT entry, stop_loss, target, qty FROM positions WHERE symbol=?", (sym,)).fetchone()
    if row and pos:
        pnl = (row["last_price"] - pos["entry"]) * pos["qty"]
        pct = (row["last_price"] - pos["entry"]) / pos["entry"] * 100
        total_pnl += pnl
        print(f"  {sym:<6} last={row['last_price']:>8.2f} entry={pos['entry']:>8.2f} qty={pos['qty']:>3.0f} pnl=${pnl:>+8.2f} ({pct:>+.2f}%) [EOD_CLOSED]")

# SNDK + SQQQ lost at stop
for sym in ["SNDK", "SQQQ"]:
    pos = conn.execute("SELECT entry, stop_loss, target, qty FROM positions WHERE symbol=?", (sym,)).fetchone()
    if pos:
        exit_p = pos["stop_loss"]
        pnl = (exit_p - pos["entry"]) * pos["qty"]
        pct = (exit_p - pos["entry"]) / pos["entry"] * 100
        total_pnl += pnl
        print(f"  {sym:<6} exit={exit_p:>8.2f} entry={pos['entry']:>8.2f} qty={pos['qty']:>3.0f} pnl=${pnl:>+8.2f} ({pct:>+.2f}%) [STOP_LOSS]")

# COIN won at target
pos = conn.execute("SELECT entry, stop_loss, target, qty FROM positions WHERE symbol=?", ("COIN",)).fetchone()
if pos:
    exit_p = pos["target"]
    pnl = (exit_p - pos["entry"]) * pos["qty"]
    pct = (exit_p - pos["entry"]) / pos["entry"] * 100
    total_pnl += pnl
    print(f"  {'COIN':<6} exit={exit_p:>8.2f} entry={pos['entry']:>8.2f} qty={pos['qty']:>3.0f} pnl=${pnl:>+8.2f} ({pct:>+.2f}%) [TARGET_HIT]")

print(f"\n  Total estimated P&L: ${total_pnl:>+.2f}")
print(f"  (EOD prices are last scan snapshot, not actual close)")
conn.close()
