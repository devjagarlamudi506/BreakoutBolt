from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from breakoutbolt.models import Position, SignalSide, SymbolSnapshot, TradeSignal


class SQLiteStore:
    def __init__(self, db_path: str, schema_path: str) -> None:
        self.db_path = db_path
        self.schema_path = schema_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(Path(self.schema_path).read_text(encoding="utf-8"))
            # Migrate: add trading_date column if missing
            for table in ("scan_snapshots", "signals", "orders"):
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                if "trading_date" not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN trading_date TEXT NOT NULL DEFAULT ''")

    def seed_watchlist(self, symbols: list[str]) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO watchlist(symbol, enabled, updated_at) VALUES (?, 1, ?)",
                [(s, now) for s in symbols],
            )

    def get_watchlist(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT symbol FROM watchlist WHERE enabled = 1 ORDER BY symbol").fetchall()
        return [r[0] for r in rows]

    def replace_watchlist(self, symbols: list[str]) -> None:
        cleaned = sorted({s.upper().strip() for s in symbols if s and s.strip()})
        if not cleaned:
            return

        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("UPDATE watchlist SET enabled = 0, updated_at = ?", (now,))
            conn.executemany(
                "INSERT OR REPLACE INTO watchlist(symbol, enabled, updated_at) VALUES (?, 1, ?)",
                [(s, now) for s in cleaned],
            )

    def save_snapshot(self, snap: SymbolSnapshot) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO scan_snapshots(
                    symbol, ts, trading_date, last_price, vwap, premarket_high,
                    trend_score, momentum_score, relative_volume,
                    intraday_volume, avg_daily_volume, dollar_volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.symbol,
                    snap.timestamp.isoformat(),
                    date.today().isoformat(),
                    snap.last_price,
                    snap.vwap,
                    snap.premarket_high,
                    snap.trend_score,
                    snap.momentum_score,
                    snap.relative_volume,
                    snap.intraday_volume,
                    snap.avg_daily_volume,
                    snap.dollar_volume,
                ),
            )

    def save_signal(self, sig: TradeSignal, ai_approved: bool, ai_note: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO signals(
                    symbol, ts, trading_date, side, pattern, entry, stop_loss,
                    target, reward_to_risk, confidence, reason,
                    ai_approved, ai_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sig.symbol,
                    sig.timestamp.isoformat(),
                    date.today().isoformat(),
                    sig.side.value,
                    sig.pattern.value,
                    sig.entry,
                    sig.stop_loss,
                    sig.target,
                    sig.reward_to_risk,
                    sig.confidence,
                    sig.reason,
                    int(ai_approved),
                    ai_note,
                ),
            )

    def open_position(self, pos: Position) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO positions(
                    symbol, side, qty, entry, stop_loss, target, opened_at, status, broker_order_id,
                    pattern, confidence, entry_vwap, entry_premarket_high,
                    entry_trend_score, entry_momentum_score, entry_relative_volume, entry_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos.symbol,
                    pos.side.value,
                    pos.qty,
                    pos.entry,
                    pos.stop_loss,
                    pos.target,
                    pos.opened_at.isoformat(),
                    pos.status,
                    pos.broker_order_id,
                    pos.pattern,
                    pos.confidence,
                    pos.entry_vwap,
                    pos.entry_premarket_high,
                    pos.entry_trend_score,
                    pos.entry_momentum_score,
                    pos.entry_relative_volume,
                    pos.entry_reason,
                ),
            )

    def close_position(self, symbol: str, status: str = "CLOSED") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE positions SET status = ?, closed_at = ? WHERE symbol = ? AND status = 'OPEN'",
                (status, datetime.utcnow().isoformat(), symbol),
            )

    def get_open_positions(self) -> list[Position]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT symbol, side, qty, entry, stop_loss, target, opened_at, status, broker_order_id,
                          pattern, confidence, entry_vwap, entry_premarket_high,
                          entry_trend_score, entry_momentum_score, entry_relative_volume, entry_reason
                   FROM positions WHERE status = 'OPEN'"""
            ).fetchall()
        results: list[Position] = []
        for row in rows:
            results.append(
                Position(
                    symbol=row[0],
                    side=SignalSide(row[1]),
                    qty=row[2],
                    entry=row[3],
                    stop_loss=row[4],
                    target=row[5],
                    opened_at=datetime.fromisoformat(row[6]),
                    status=row[7],
                    broker_order_id=row[8],
                    pattern=row[9],
                    confidence=row[10],
                    entry_vwap=row[11],
                    entry_premarket_high=row[12],
                    entry_trend_score=row[13],
                    entry_momentum_score=row[14],
                    entry_relative_volume=row[15],
                    entry_reason=row[16],
                )
            )
        return results

    def log_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        status: str,
        broker_order_id: str | None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO orders(symbol, side, qty, order_type, status, broker_order_id, submitted_at, trading_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, side, qty, order_type, status, broker_order_id, datetime.utcnow().isoformat(), date.today().isoformat()),
            )

    def clear_daily_data(self) -> None:
        """Close leftover open positions and prune data older than 5 days."""
        now = datetime.utcnow().isoformat()
        cutoff = (date.today() - timedelta(days=5)).isoformat()
        with self._conn() as conn:
            conn.execute("UPDATE positions SET status = 'EOD_CLOSED', closed_at = ? WHERE status = 'OPEN'", (now,))
            conn.execute("DELETE FROM scan_snapshots WHERE trading_date < ?", (cutoff,))
            conn.execute("DELETE FROM signals WHERE trading_date < ?", (cutoff,))
            conn.execute("DELETE FROM orders WHERE trading_date < ?", (cutoff,))

    def get_recent_signals(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT symbol, ts, side, pattern, entry, stop_loss, target, reward_to_risk, confidence, reason, ai_approved, ai_note
                FROM signals ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "symbol": r[0],
                "timestamp": r[1],
                "side": r[2],
                "pattern": r[3],
                "entry": r[4],
                "stop_loss": r[5],
                "target": r[6],
                "reward_to_risk": r[7],
                "confidence": r[8],
                "reason": r[9],
                "ai_approved": bool(r[10]),
                "ai_note": r[11],
            }
            for r in rows
        ]
