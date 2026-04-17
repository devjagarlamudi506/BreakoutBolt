"""Pull P&L from Alpaca closed orders for today."""
import os, asyncio
from dotenv import load_dotenv
load_dotenv()

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, QueryOrderStatus

client = TradingClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET"),
    paper=True,
)

# Get account
acct = client.get_account()
print(f"Account equity:     ${float(acct.equity):,.2f}")
print(f"Cash:               ${float(acct.cash):,.2f}")
print(f"Buying power:       ${float(acct.buying_power):,.2f}")
print(f"Portfolio value:    ${float(acct.portfolio_value):,.2f}")
print(f"Last equity:        ${float(acct.last_equity):,.2f}")
pnl = float(acct.equity) - float(acct.last_equity)
print(f"Day P&L:            ${pnl:,.2f} ({pnl/float(acct.last_equity)*100:+.2f}%)")
print()

# Get all closed orders
req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=50)
orders = client.get_orders(req)

print(f"{'Side':<5} {'Symbol':<7} {'Qty':>5} {'Fill$':>9} {'Filled':>20}")
print("-" * 55)
buys = {}
sells = {}
for o in sorted(orders, key=lambda x: x.filled_at or x.submitted_at):
    if o.filled_avg_price is None:
        continue
    fill = float(o.filled_avg_price)
    qty = float(o.filled_qty)
    ts = str(o.filled_at)[:19] if o.filled_at else "pending"
    print(f"{o.side:<5} {o.symbol:<7} {qty:>5.0f} {fill:>9.2f} {ts:>20}")
    
    if str(o.side) == "OrderSide.BUY":
        buys[o.symbol] = (fill, qty)
    else:
        sells.setdefault(o.symbol, []).append((fill, qty))

print(f"\n{'='*55}")
print(f"  REALIZED P&L PER POSITION")
print(f"{'='*55}")

total_pnl = 0
for sym, sell_list in sells.items():
    if sym in buys:
        buy_price, buy_qty = buys[sym]
        for sell_price, sell_qty in sell_list:
            pnl = (sell_price - buy_price) * sell_qty
            total_pnl += pnl
            pct = (sell_price - buy_price) / buy_price * 100
            print(f"  {sym:<7} bought@{buy_price:.2f} sold@{sell_price:.2f} qty={sell_qty:.0f} P&L=${pnl:>+8.2f} ({pct:+.2f}%)")

print(f"\n  Total realized P&L: ${total_pnl:>+.2f}")

# Open positions
positions = client.get_all_positions()
if positions:
    print(f"\n{'='*55}")
    print(f"  OPEN POSITIONS (still held)")
    print(f"{'='*55}")
    unrealized = 0
    for p in positions:
        upl = float(p.unrealized_pl)
        unrealized += upl
        print(f"  {p.symbol:<7} qty={float(p.qty):.0f} entry={float(p.avg_entry_price):.2f} current={float(p.current_price):.2f} P&L=${upl:>+.2f}")
    print(f"\n  Total unrealized P&L: ${unrealized:>+.2f}")
else:
    print(f"\n  No open positions (all flat)")
