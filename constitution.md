Build an intraday NASDAQ momentum trading system called BreakoutBolt with the following architecture and constraints:

Goal
Create a bot that scans a reduced universe of high-liquidity NASDAQ stocks during market hours, identifies only the cleanest breakout or pullback setups, and sends disciplined BUY / SELL / HOLD signals with strict risk control. The system should prioritize signal quality over signal quantity and must avoid overtrading, duplicate entries, and noisy alerts.

Core strategy
Use a two-stage decision pipeline:

Deterministic screening to filter symbols by liquidity, relative volume, trend direction, VWAP position, breakout strength, and momentum persistence.

Light AI validation only on the final shortlist to approve or reject a setup.

Only trade one or two simple patterns, such as:

breakout continuation above VWAP or a premarket high,

pullback-to-VWAP in a strong trend.

If the setup is unclear, return HOLD. Do not force trades.

Risk rules
Every signal must include:

entry price,

stop-loss,

profit target,

reward-to-risk ratio,

confidence score,

reason for the signal.

Reject any signal that does not satisfy minimum liquidity, volume, and reward-to-risk thresholds. Do not enter trades without valid exits and risk controls.

Trading behavior
Run scanning repeatedly during trading hours.

Track active positions and current signal state.

Prevent duplicate re-entry alerts for the same symbol.

Generate exit alerts when stop-loss or target is hit.

Use paper trading by default.

Optionally execute live trades through Alpaca only when explicitly enabled.

Notifications
Send approved signals and exit events to Discord in a clean structured format. Include symbol, side, entry, stop, target, risk/reward, and justification. The Discord bot should also be able to show current watchlist status and active positions.

Stack
Use this stack:

Python for the bot and strategy engine,

Alpaca API for market data, paper trading, and live execution,

Discord bot for alerts and monitoring,

SQLite for local persistent storage of watchlists, signals, positions, and trade history,

Redis for caching market state, recent scans, duplicate-signal suppression, and fast runtime coordination,

FastAPI for API endpoints, health checks, and manual control,

Polygon for market data for real-time updates,

Pandas / NumPy for calculations and indicator processing.

System design
Split the application into clear modules:

market data collector,

signal engine,

risk manager,

AI review layer,

order execution service,

position tracker,

alert dispatcher,

persistence layer,

API layer.

Use SQLite as the main durable database for intraday data, trade logs, and bot state. Keep Redis only for temporary runtime state, fast lookups, and duplicate alert suppression. Design the code so each module can be tested independently and the bot can run continuously without blocking.

Execution rules
Use Alpaca paper trading in development.

Include safe defaults and environment-based configuration.

Log every signal decision and order action.

Make the system resilient to API failures, missing data, duplicate events, and temporary network interruptions.

Keep the code clean, modular, and production-oriented.

Store day-level data locally in SQLite so the bot can restart without losing intraday history.

Deliverable
Generate the full codebase structure, main Python files, SQLite schema, and Discord alert format for this system.