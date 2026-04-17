CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts TEXT NOT NULL,
    trading_date TEXT NOT NULL DEFAULT '',
    last_price REAL NOT NULL,
    vwap REAL NOT NULL,
    premarket_high REAL NOT NULL,
    trend_score REAL NOT NULL,
    momentum_score REAL NOT NULL,
    relative_volume REAL NOT NULL,
    intraday_volume REAL NOT NULL,
    avg_daily_volume REAL NOT NULL,
    dollar_volume REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scan_snapshots_symbol_ts ON scan_snapshots(symbol, ts);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    ts TEXT NOT NULL,
    trading_date TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL,
    pattern TEXT NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target REAL NOT NULL,
    reward_to_risk REAL NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    ai_approved INTEGER NOT NULL,
    ai_note TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_ts ON signals(symbol, ts);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    target REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    status TEXT NOT NULL,
    broker_order_id TEXT,
    pattern TEXT,
    confidence REAL,
    entry_vwap REAL,
    entry_premarket_high REAL,
    entry_trend_score REAL,
    entry_momentum_score REAL,
    entry_relative_volume REAL,
    entry_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_symbol_open ON positions(symbol) WHERE status = 'OPEN';

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    order_type TEXT NOT NULL,
    status TEXT NOT NULL,
    broker_order_id TEXT,
    submitted_at TEXT NOT NULL,
    trading_date TEXT NOT NULL DEFAULT ''
);
