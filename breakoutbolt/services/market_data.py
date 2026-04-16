from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx
import numpy as np
import pandas as pd

from breakoutbolt.models import SymbolSnapshot

logger = logging.getLogger(__name__)


class MarketDataCollector:
    def __init__(self, polygon_api_key: str, polygon_base_url: str) -> None:
        self.polygon_api_key = polygon_api_key
        self.polygon_base_url = polygon_base_url.rstrip("/")

    async def fetch_snapshots(self, symbols: list[str]) -> dict[str, SymbolSnapshot | None]:
        """Fetch snapshots for all symbols concurrently."""
        tasks = {symbol: self.fetch_snapshot(symbol) for symbol in symbols}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        out: dict[str, SymbolSnapshot | None] = {}
        for symbol, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning("Parallel fetch failed for %s: %s", symbol, result)
                out[symbol] = None
            else:
                out[symbol] = result
        return out

    async def fetch_snapshot(self, symbol: str) -> SymbolSnapshot | None:
        if not self.polygon_api_key:
            return self._mock_snapshot(symbol)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        url = f"{self.polygon_base_url}/v2/aggs/ticker/{symbol}/range/1/minute/{today}/{today}"
        params = {"adjusted": "true", "sort": "asc", "limit": 200, "apiKey": self.polygon_api_key}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
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
            )
        except Exception as exc:
            logger.warning("Polygon fetch failed for %s: %s", symbol, exc)
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
