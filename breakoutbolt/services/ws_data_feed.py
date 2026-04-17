from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import numpy as np
import websockets

from breakoutbolt.models import SymbolSnapshot

logger = logging.getLogger(__name__)

FINNHUB_WS_URL = "wss://ws.finnhub.io"
MAX_SYMBOLS = 50  # Finnhub free tier limit


class _BarBuilder:
    """Aggregates raw trades into 1-minute OHLCV bars for a single symbol."""

    __slots__ = ("open", "high", "low", "close", "volume", "vwap_num", "minute_key")

    def __init__(self) -> None:
        self.open = 0.0
        self.high = 0.0
        self.low = 0.0
        self.close = 0.0
        self.volume = 0.0
        self.vwap_num = 0.0  # sum(price * volume)
        self.minute_key = 0  # unix minute (timestamp // 60)

    def update(self, price: float, vol: float, ts_ms: int) -> dict | None:
        """Feed a trade. Returns a completed bar dict when a new minute starts."""
        minute = ts_ms // 60_000
        completed = None

        if self.minute_key and minute != self.minute_key and self.volume > 0:
            completed = self._finalize()

        if minute != self.minute_key:
            # Start new bar
            self.minute_key = minute
            self.open = price
            self.high = price
            self.low = price
            self.close = price
            self.volume = vol
            self.vwap_num = price * vol
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
            self.close = price
            self.volume += vol
            self.vwap_num += price * vol

        return completed

    def _finalize(self) -> dict:
        vw = self.vwap_num / self.volume if self.volume > 0 else self.close
        return {
            "o": self.open,
            "h": self.high,
            "l": self.low,
            "c": self.close,
            "v": self.volume,
            "vw": vw,
        }


class WsDataFeed:
    """Real-time data via Finnhub WebSocket for signal scanning.

    Subscribes to trade updates for the active watchlist (up to 50 symbols),
    aggregates trades into 1-minute bars, and produces SymbolSnapshot objects
    with real-time prices for the signal engine.
    """

    def __init__(self, finnhub_api_key: str) -> None:
        self.api_key = finnhub_api_key
        self._bars: dict[str, list[dict]] = {}          # accumulated completed bars
        self._builders: dict[str, _BarBuilder] = {}      # live bar builders
        self._latest_price: dict[str, float] = {}
        self._ws = None
        self._subscribed: set[str] = set()
        self._target_symbols: set[str] = set()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Connect, subscribe, and stream. Auto-reconnects."""
        while True:
            try:
                url = f"{FINNHUB_WS_URL}?token={self.api_key}"
                async with websockets.connect(url) as ws:
                    self._ws = ws
                    await self._resync()
                    logger.info("Finnhub WS data feed connected (%d symbols)", len(self._target_symbols))
                    async for raw in ws:
                        self._handle_message(raw)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as exc:
                logger.warning("Finnhub WS data feed disconnected: %s — reconnecting in 5s", exc)
            except Exception as exc:
                logger.exception("Finnhub WS data feed error: %s", exc)
            self._ws = None
            self._subscribed.clear()
            await asyncio.sleep(5)

    async def _resync(self) -> None:
        """Re-subscribe to all target symbols after (re)connect."""
        if not self._ws or not self._target_symbols:
            return
        for sym in self._target_symbols:
            await self._ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
        self._subscribed = set(self._target_symbols)

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def update_subscriptions(self, symbols: list[str]) -> None:
        """Called when watchlist changes. Updates trade subscriptions (max 50)."""
        new_set = set(symbols[:MAX_SYMBOLS])
        if new_set == self._target_symbols:
            return

        old = self._target_symbols
        self._target_symbols = new_set

        to_unsub = old - new_set
        to_sub = new_set - old

        if to_unsub and self._ws:
            for sym in to_unsub:
                await self._ws.send(json.dumps({"type": "unsubscribe", "symbol": sym}))
            self._subscribed -= to_unsub
            for s in to_unsub:
                self._bars.pop(s, None)
                self._builders.pop(s, None)
                self._latest_price.pop(s, None)

        if to_sub and self._ws:
            for sym in to_sub:
                await self._ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
            self._subscribed |= to_sub

        if to_sub or to_unsub:
            logger.info("Finnhub WS data feed updated: +%d -%d symbols (total: %d)",
                        len(to_sub), len(to_unsub), len(self._target_symbols))

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Unparseable Finnhub WS message: %s", raw[:200])
            return

        if msg.get("type") == "ping":
            return  # heartbeat, ignore

        if msg.get("type") != "trade":
            return

        trades = msg.get("data", [])
        for trade in trades:
            symbol = trade.get("s")
            price = trade.get("p")
            volume = trade.get("v", 0)
            ts_ms = trade.get("t", int(time.time() * 1000))

            if not symbol or price is None:
                continue

            self._latest_price[symbol] = price

            builder = self._builders.get(symbol)
            if not builder:
                builder = _BarBuilder()
                self._builders[symbol] = builder

            completed_bar = builder.update(price, volume, ts_ms)
            if completed_bar:
                self._bars.setdefault(symbol, []).append(completed_bar)
                # Cap at ~420 bars (full trading day = 390 1-min bars + buffer)
                if len(self._bars[symbol]) > 420:
                    self._bars[symbol] = self._bars[symbol][-400:]

    # ------------------------------------------------------------------
    # Snapshot computation
    # ------------------------------------------------------------------

    def get_snapshot(self, symbol: str) -> SymbolSnapshot | None:
        """Build a SymbolSnapshot from accumulated real-time bars.

        Falls back to a minimal snapshot from the live (partial) bar
        when no completed bars exist yet.
        """
        last_price = self._latest_price.get(symbol)
        if last_price is None:
            return None

        bars = self._bars.get(symbol, [])

        # Include the in-progress bar so we have data even before the first
        # minute boundary completes.
        live_builder = self._builders.get(symbol)
        if live_builder and live_builder.volume > 0:
            live_bar = {
                "o": live_builder.open,
                "h": live_builder.high,
                "l": live_builder.low,
                "c": live_builder.close,
                "v": live_builder.volume,
                "vw": live_builder.vwap_num / max(live_builder.volume, 1e-9),
            }
            all_bars = bars + [live_bar]
        else:
            all_bars = bars

        if not all_bars:
            return None

        closes = np.array([b["c"] for b in all_bars], dtype=float)
        highs = np.array([b["h"] for b in all_bars], dtype=float)
        lows = np.array([b["l"] for b in all_bars], dtype=float)
        volumes = np.array([b["v"] for b in all_bars], dtype=float)
        vwaps = np.array([b.get("vw", b["c"]) for b in all_bars], dtype=float)

        total_vol = float(volumes.sum())
        day_vwap = float((vwaps * volumes).sum() / max(total_vol, 1.0))

        # Trend: intraday return from first bar to current
        trend_score = float((last_price / closes[0]) - 1) if closes[0] > 0 else 0.0

        # Momentum: change over last 30 bars (~30 min)
        lookback = min(30, len(closes) - 1)
        ref = float(closes[-1 - lookback]) if lookback > 0 else float(closes[0])
        momentum_score = float((last_price / ref) - 1) if ref > 0 else 0.0

        # Relative volume: recent 30 bars vs first 30 bars of session
        if len(volumes) > 60:
            rel_vol = float(volumes[-30:].sum() / max(volumes[:30].sum(), 1.0))
        else:
            rel_vol = 1.5  # not enough bars yet; use neutral default

        last_bar = all_bars[-1]

        # Multi-bar context for signal quality
        bar_count = len(all_bars)

        # Consecutive green/red bars (close > open = green)
        consecutive_green = 0
        consecutive_red = 0
        for b in reversed(all_bars):
            if b["c"] > b["o"]:
                if consecutive_red == 0:
                    consecutive_green += 1
                else:
                    break
            elif b["c"] < b["o"]:
                if consecutive_green == 0:
                    consecutive_red += 1
                else:
                    break
            else:
                break

        # ATR: average true range of last 14 bars
        if len(all_bars) >= 2:
            trs = []
            for i in range(1, min(15, len(all_bars))):
                prev_c = all_bars[i - 1]["c"]
                curr_h = all_bars[i]["h"]
                curr_l = all_bars[i]["l"]
                tr = max(curr_h - curr_l, abs(curr_h - prev_c), abs(curr_l - prev_c))
                trs.append(tr)
            atr = float(np.mean(trs)) if trs else 0.0
        else:
            atr = float(all_bars[0]["h"] - all_bars[0]["l"])

        # Volume surge: last bar volume vs average bar volume
        if bar_count >= 5:
            avg_bar_vol = float(volumes[:-1].mean()) if len(volumes) > 1 else 1.0
            vol_surge = float(volumes[-1] / max(avg_bar_vol, 1.0))
        else:
            vol_surge = 1.0

        return SymbolSnapshot(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            last_price=last_price,
            vwap=day_vwap,
            premarket_high=float(highs.max()),  # session high
            trend_score=trend_score,
            momentum_score=momentum_score,
            relative_volume=rel_vol,
            avg_daily_volume=total_vol,
            intraday_volume=total_vol,
            bar_high=float(last_bar.get("h", last_price)),
            bar_low=float(last_bar.get("l", last_price)),
            bar_count=bar_count,
            consecutive_green_bars=consecutive_green,
            consecutive_red_bars=consecutive_red,
            atr=atr,
            volume_surge=vol_surge,
        )

    def has_data(self, symbol: str) -> bool:
        """True if we have any real-time price for the symbol."""
        return symbol in self._latest_price

    def clear_day(self) -> None:
        """Clear accumulated bars at end of day."""
        self._bars.clear()
        self._builders.clear()
        self._latest_price.clear()
