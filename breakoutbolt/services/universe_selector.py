from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import numpy as np

from breakoutbolt.config import Settings

logger = logging.getLogger(__name__)

# Polygon Starter plan: ~5 requests/second. Use 4/sec to leave headroom.
_POLYGON_MAX_PER_SEC = 4


class UniverseSelector:
    """Multi-factor universe selector: relative volume, ATR%, momentum, gap screening."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pg_timestamps: list[float] = []
        self._pg_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None
        self.daily_volumes: dict[str, float] = {}

    async def build_watchlist(self) -> list[str]:
        if not self.settings.dynamic_watchlist_enabled:
            logger.info("Dynamic watchlist disabled, using static fallback")
            return self.settings.watchlist
        if not self.settings.polygon_api_key:
            logger.info("No Polygon API key, using static fallback")
            return self.settings.watchlist

        try:
            symbols = await self._build_composite_universe()
            if symbols:
                logger.info("Dynamic watchlist built (%d symbols): %s", len(symbols), symbols)
                return symbols
            logger.warning("No qualifying candidates, using static fallback")
        except Exception as exc:
            logger.warning("Dynamic watchlist refresh failed: %s", exc)

        return self.settings.watchlist

    # ------------------------------------------------------------------
    # Composite multi-factor pipeline
    # ------------------------------------------------------------------

    async def _build_composite_universe(self) -> list[str]:
        prev_day = self._previous_trading_day()
        lookback_start = prev_day - timedelta(days=30)  # ~20 trading days

        # During market hours, fetch TODAY's running intraday aggregates so the
        # watchlist evolves with real-time volume and price action.  Fall back to
        # the previous session when the market is closed (e.g. pre-market).
        today = date.today()
        latest_bars = await self._fetch_grouped_daily(today)
        if not latest_bars:
            logger.info("No intraday data for today yet, falling back to previous day")
            latest_bars = await self._fetch_grouped_daily(prev_day)
        if not latest_bars:
            return []

        # Pre-filter: alpha-only symbols, 1-5 chars, minimum price & dollar volume.
        candidates: dict[str, dict] = {}
        for bar in latest_bars:
            symbol = str(bar.get("T", "")).upper()
            if not symbol or not symbol.isalpha() or len(symbol) > 5:
                continue
            close = float(bar.get("c", 0))
            volume = float(bar.get("v", 0))
            if close < self.settings.universe_min_price:
                continue
            dollar_vol = close * volume
            if dollar_vol < self.settings.min_dollar_volume:
                continue
            candidates[symbol] = {
                "close": close,
                "open": float(bar.get("o", close)),
                "high": float(bar.get("h", close)),
                "low": float(bar.get("l", close)),
                "volume": volume,
                "dollar_volume": dollar_vol,
            }

        logger.info("Pre-filter passed %d tickers for scoring", len(candidates))
        if not candidates:
            return []

        # Narrow to top candidates by dollar volume before fetching history.
        # At ~4 req/sec rate limit, 60 symbols ≈ 15 seconds — acceptable.
        shortlist_size = min(self.settings.watchlist_size * 2, 60)  # e.g. 60 for top 30
        sorted_by_dv = sorted(candidates.keys(), key=lambda s: candidates[s]["dollar_volume"], reverse=True)
        shortlist = sorted_by_dv[:shortlist_size]
        logger.info("Shortlisted %d tickers for history fetch", len(shortlist))

        # Fetch 20-day daily bars for shortlisted candidates.
        history = await self._fetch_daily_history(
            shortlist, lookback_start, prev_day
        )

        # Score each candidate.
        scored: list[tuple[str, float]] = []
        for symbol, latest in candidates.items():
            bars = history.get(symbol)
            if not bars or len(bars) < 5:
                continue

            closes = np.array([b["c"] for b in bars], dtype=float)
            highs = np.array([b["h"] for b in bars], dtype=float)
            lows = np.array([b["l"] for b in bars], dtype=float)
            volumes = np.array([b["v"] for b in bars], dtype=float)

            # --- Factor 1: Relative volume (prev day vs 20-day avg) ---
            # Normalize for time-of-day: at 9:45 ET only ~15 min of volume exists.
            avg_vol = float(np.mean(volumes)) if len(volumes) > 0 else 1.0
            now_et = datetime.now(ZoneInfo("America/New_York"))
            minutes_in = max((now_et.hour * 60 + now_et.minute) - (9 * 60 + 30), 1)
            day_fraction = min(minutes_in / 390, 1.0)
            proportional_avg = avg_vol * day_fraction
            rel_vol = latest["volume"] / max(proportional_avg, 1.0)

            # --- Factor 2: ATR% (14-period ATR as % of price) ---
            tr = np.maximum(
                highs[1:] - lows[1:],
                np.maximum(
                    np.abs(highs[1:] - closes[:-1]),
                    np.abs(lows[1:] - closes[:-1]),
                ),
            )
            atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else float(np.mean(tr))
            atr_pct = (atr / latest["close"]) * 100

            # --- Factor 3: 5-day momentum (% change) ---
            if len(closes) >= 6:
                momentum = (closes[-1] / closes[-6] - 1) * 100
            else:
                momentum = 0.0

            # --- Factor 4: Gap % (open vs prior close) ---
            if len(closes) >= 2:
                gap_pct = abs((latest["open"] / closes[-2] - 1) * 100)
            else:
                gap_pct = 0.0

            # Apply minimum thresholds.
            if rel_vol < self.settings.universe_min_rel_vol:
                continue
            if atr_pct < self.settings.universe_min_atr_pct:
                continue

            # Composite score (weighted sum of normalized factors).
            score = (
                self.settings.weight_rel_vol * min(rel_vol, 10.0)
                + self.settings.weight_atr_pct * min(atr_pct, 15.0)
                + self.settings.weight_momentum * min(abs(momentum), 20.0)
                + self.settings.weight_gap * min(gap_pct, 10.0)
                + self.settings.weight_dollar_vol * min(latest["dollar_volume"] / 1e9, 5.0)
            )

            scored.append((symbol, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = [s for s, _ in scored[: self.settings.watchlist_size]]
        self.daily_volumes = {s: candidates[s]["volume"] for s in top if s in candidates}
        logger.info(
            "Scored %d candidates, top 5: %s",
            len(scored),
            [(s, round(sc, 2)) for s, sc in scored[:5]],
        )
        return top

    # ------------------------------------------------------------------
    # Polygon API helpers
    # ------------------------------------------------------------------

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=15.0)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def _acquire_polygon_token(self) -> None:
        """Sliding-window rate limiter: max _POLYGON_MAX_PER_SEC calls per second."""
        async with self._pg_lock:
            now = time.monotonic()
            cutoff = now - 1.0
            self._pg_timestamps = [t for t in self._pg_timestamps if t > cutoff]
            if len(self._pg_timestamps) >= _POLYGON_MAX_PER_SEC:
                wait = self._pg_timestamps[0] - cutoff
                if wait > 0:
                    logger.debug("Polygon rate limit: waiting %.2fs", wait)
                    await asyncio.sleep(wait)
                    self._pg_timestamps = [t for t in self._pg_timestamps if t > time.monotonic() - 1.0]
            self._pg_timestamps.append(time.monotonic())

    @staticmethod
    def _previous_trading_day() -> date:
        d = date.today() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d

    async def _fetch_grouped_daily(self, target_date: date) -> list[dict]:
        await self._acquire_polygon_token()
        base = self.settings.polygon_base_url.rstrip("/")
        url = f"{base}/v2/aggs/grouped/locale/us/market/stocks/{target_date.isoformat()}"
        params = {"adjusted": "true", "apiKey": self.settings.polygon_api_key}
        client = await self._get_http()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results", [])
        logger.info("Grouped daily returned %d tickers for %s", len(results), target_date)
        return results

    async def _fetch_daily_history(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[dict]]:
        """Fetch 20-day daily bars for each symbol. Rate-limited to Polygon Starter plan."""
        base = self.settings.polygon_base_url.rstrip("/")
        client = await self._get_http()
        out: dict[str, list[dict]] = {}

        for symbol in symbols:
            await self._acquire_polygon_token()
            url = f"{base}/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
            params = {"adjusted": "true", "sort": "asc", "limit": 30, "apiKey": self.settings.polygon_api_key}
            try:
                resp = await client.get(url, params=params)
                if resp.status_code == 429:
                    logger.warning("Polygon rate-limited on %s, skipping remaining history", symbol)
                    break
                resp.raise_for_status()
                out[symbol] = resp.json().get("results", [])
            except Exception as exc:
                logger.debug("History fetch failed for %s: %s", symbol, exc)
                out[symbol] = []

        return out
