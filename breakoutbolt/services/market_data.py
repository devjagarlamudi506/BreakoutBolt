from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import httpx
import numpy as np
import pandas as pd

from breakoutbolt.models import SymbolSnapshot

logger = logging.getLogger(__name__)


class MarketDataCollector:
    # Finnhub free tier: 60 API calls per minute.
    # Use 55 to leave headroom for occasional retries.
    _FINNHUB_RPM = 55

    def __init__(self, polygon_api_key: str, polygon_base_url: str, finnhub_api_key: str = "") -> None:
        self.polygon_api_key = polygon_api_key
        self.polygon_base_url = polygon_base_url.rstrip("/")
        self.finnhub_api_key = finnhub_api_key
        self._http: httpx.AsyncClient | None = None
        # Sliding-window rate limiter: track timestamps of recent Finnhub calls
        self._fh_timestamps: list[float] = []
        self._fh_lock = asyncio.Lock()

    async def _get_http(self) -> httpx.AsyncClient:
        """Reuse a single httpx client for connection pooling."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=8.0)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def fetch_snapshots(self, symbols: list[str], *, skip_finnhub: bool = False) -> dict[str, SymbolSnapshot | None]:
        """Fetch snapshots for all symbols concurrently."""
        tasks = {symbol: self.fetch_snapshot(symbol, skip_finnhub=skip_finnhub) for symbol in symbols}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        out: dict[str, SymbolSnapshot | None] = {}
        for symbol, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning("Parallel fetch failed for %s: %s", symbol, result)
                out[symbol] = None
            else:
                out[symbol] = result
        return out

    async def fetch_snapshot(self, symbol: str, *, skip_finnhub: bool = False) -> SymbolSnapshot | None:
        if not self.polygon_api_key and not self.finnhub_api_key:
            return self._mock_snapshot(symbol)

        # Try Finnhub Quote first (real-time, 60 calls/min)
        if self.finnhub_api_key and not skip_finnhub:
            snap = await self._fetch_finnhub_quote(symbol)
            if snap:
                return snap

        # Fallback to Polygon 1-min bars (15-min delayed)
        if not self.polygon_api_key:
            return None
        today = datetime.utcnow().strftime("%Y-%m-%d")
        url = f"{self.polygon_base_url}/v2/aggs/ticker/{symbol}/range/1/minute/{today}/{today}"
        params = {"adjusted": "true", "sort": "asc", "limit": 200, "apiKey": self.polygon_api_key}
        try:
            client = await self._get_http()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("results", [])
            if not rows:
                return None
            frame = pd.DataFrame(rows)
            frame = frame.rename(columns={"c": "close", "h": "high", "l": "low", "v": "volume"})
            close = frame["close"].astype(float)
            high = frame["high"].astype(float)
            volume = frame["volume"].astype(float)
            last = frame.iloc[-1]  # most recent bar (sorted asc)
            vwap = float((close * volume).sum() / max(volume.sum(), 1.0))
            returns = close.pct_change().fillna(0)
            trend_score = float((close.iloc[-1] / close.iloc[0]) - 1)
            momentum_score = float(returns.tail(15).mean() / (returns.std() + 1e-6))
            # relative volume: recent 30 bars vs older 30 bars
            rel_vol = float(volume.tail(30).sum() / max(volume.head(30).sum(), 1.0))
            return SymbolSnapshot(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                last_price=float(last["close"]),
                vwap=vwap,
                premarket_high=float(high.max()),
                trend_score=trend_score,
                momentum_score=momentum_score,
                relative_volume=max(rel_vol, 0.1),
                avg_daily_volume=float(volume.mean() * 390),
                intraday_volume=float(volume.sum()),
                bar_high=float(last["high"]),
                bar_low=float(last["low"]),
            )
        except Exception as exc:
            logger.warning("Polygon fetch failed for %s: %s", symbol, exc)
            return None

    async def _acquire_finnhub_token(self) -> None:
        """Sliding-window rate limiter: max _FINNHUB_RPM calls per 60 seconds."""
        async with self._fh_lock:
            now = time.monotonic()
            # Evict timestamps older than 60 seconds
            cutoff = now - 60.0
            self._fh_timestamps = [t for t in self._fh_timestamps if t > cutoff]
            if len(self._fh_timestamps) >= self._FINNHUB_RPM:
                # Wait until the oldest call exits the window
                wait = self._fh_timestamps[0] - cutoff
                if wait > 0:
                    logger.debug("Finnhub rate limit: waiting %.1fs", wait)
                    await asyncio.sleep(wait)
                    self._fh_timestamps = [t for t in self._fh_timestamps if t > time.monotonic() - 60.0]
            self._fh_timestamps.append(time.monotonic())

    async def _fetch_finnhub_quote(self, symbol: str) -> SymbolSnapshot | None:
        """Fetch real-time quote from Finnhub free tier (60 calls/min)."""
        await self._acquire_finnhub_token()
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": self.finnhub_api_key}
        try:
            client = await self._get_http()
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                logger.warning("Finnhub rate-limited for %s, skipping", symbol)
                return None
            resp.raise_for_status()
            q = resp.json()
            # q: {"c": current, "d": change, "dp": pct_change, "h": high, "l": low, "o": open, "pc": prev_close}
            current = q.get("c", 0)
            if not current or current == 0:
                return None
            day_high = q.get("h", current)
            day_low = q.get("l", current)
            day_open = q.get("o", current)
            prev_close = q.get("pc", current)
            trend_score = (current / day_open - 1) if day_open > 0 else 0.0
            return SymbolSnapshot(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                last_price=float(current),
                vwap=float((day_high + day_low + current) / 3),  # typical price approximation
                premarket_high=float(day_high),
                trend_score=float(trend_score),
                momentum_score=float(current / prev_close - 1) if prev_close > 0 else 0.0,
                relative_volume=1.5,  # Quote doesn't include volume; use neutral default
                avg_daily_volume=0.0,
                intraday_volume=0.0,
                bar_high=float(day_high),
                bar_low=float(day_low),
            )
        except Exception as exc:
            logger.warning("Finnhub quote failed for %s: %s", symbol, exc)
            return None

    def _mock_snapshot(self, symbol: str) -> SymbolSnapshot:
        # Fallback keeps the system testable without external APIs.
        seed = sum(ord(c) for c in symbol)
        rng = np.random.default_rng(seed + int(datetime.utcnow().timestamp() // 60))
        base = float(rng.uniform(20, 700))
        drift = float(rng.normal(0.001, 0.004))
        vol = float(rng.uniform(1.0, 3.5))
        intraday_volume = float(rng.uniform(200_000, 5_000_000))
        last = base * (1 + drift)
        return SymbolSnapshot(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            last_price=last,
            vwap=last * (1 - float(rng.uniform(-0.01, 0.01))),
            premarket_high=last * (1 + float(rng.uniform(0.001, 0.015))),
            trend_score=float(rng.uniform(-0.03, 0.06)),
            momentum_score=float(rng.normal(0.4, 0.9)),
            relative_volume=vol,
            avg_daily_volume=intraday_volume * float(rng.uniform(2.0, 6.0)),
            intraday_volume=intraday_volume,
        )
