# BreakoutBolt Architecture

Modules:
- market data collector: Polygon-first with mock fallback.
- signal engine: deterministic filters and pattern detection.
- risk manager: validates exits and reward/risk constraints.
- AI review layer: light confidence gate for shortlist.
- order execution service: Alpaca integration with paper/live safety.
- position tracker: stop and target monitoring.
- alert dispatcher: Discord structured webhook notifications.
- persistence layer: SQLite for durable state and trade history.
- cache layer: Redis (with memory fallback) for runtime suppression.
- API layer: FastAPI health/status/manual control endpoints.

Runtime:
- `run_bot.py` runs the intraday scan loop.
- `main.py` exposes FastAPI app (`uvicorn main:app`).
