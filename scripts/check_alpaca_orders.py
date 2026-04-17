"""Check Alpaca orders from today specifically."""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest, QueryOrderStatus

client = TradingClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET"),
    paper=True,
)

# All orders (any status) from last 2 days
after = datetime.utcnow() - timedelta(days=2)
for status in [QueryOrderStatus.ALL]:
    req = GetOrdersRequest(status=status, limit=100, after=after)
    orders = client.get_orders(req)
    print(f"Orders with status={status}: {len(orders)}")
    for o in sorted(orders, key=lambda x: x.submitted_at):
        fill = float(o.filled_avg_price) if o.filled_avg_price else 0
        print(f"  {str(o.submitted_at)[:19]} | {o.side} {o.symbol:<7} qty={o.qty} fill=${fill:.2f} status={o.status} id={str(o.id)[:8]}")

# Also check activity
print(f"\nAccount activities:")
try:
    activities = client.get_activities(activity_types=["FILL"])
    for a in list(activities)[:20]:
        print(f"  {a}")
except Exception as e:
    print(f"  Error: {e}")
