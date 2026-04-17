from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from breakoutbolt.config import Settings
from breakoutbolt.db.sqlite_store import SQLiteStore
from breakoutbolt.models import Position
from breakoutbolt.services.ai_review import AIReviewLayer
from breakoutbolt.services.alert_dispatcher import AlertDispatcher
from breakoutbolt.services.execution import OrderExecutionService
from breakoutbolt.services.market_data import MarketDataCollector
from breakoutbolt.services.position_tracker import PositionTracker
from breakoutbolt.services.risk_manager import RiskManager
from breakoutbolt.services.signal_engine import SignalEngine
from breakoutbolt.services.state_cache import StateCache
from breakoutbolt.services.universe_selector import UniverseSelector

logger = logging.getLogger(__name__)


class BreakoutBoltOrchestrator:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        data_collector: MarketDataCollector,
        signal_engine: SignalEngine,
        risk_manager: RiskManager,
        ai_review: AIReviewLayer,
        execution: OrderExecutionService,
        tracker: PositionTracker,
        alerts: AlertDispatcher,
        cache: StateCache,
        universe_selector: UniverseSelector,
    ) -> None:
        self.settings = settings
        self.store = store
        self.data_collector = data_collector
        self.signal_engine = signal_engine
        self.risk_manager = risk_manager
        self.ai_review = ai_review
        self.execution = execution
        self.tracker = tracker
        self.alerts = alerts
        self.cache = cache
        self.universe_selector = universe_selector
        self._last_watchlist_refresh: datetime | None = None
        self._daily_volumes: dict[str, float] = {}
        self.ws_monitor = None  # set externally when websocket_exit_enabled
        self.ws_data_feed = None  # set externally for real-time signal scanning

    def market_is_open(self) -> bool:
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.weekday() >= 5:
            return False
        open_minutes = self.settings.market_open_hour_et * 60 + self.settings.market_open_minute_et
        close_minutes = self.settings.market_close_hour_et * 60
        now_minutes = now.hour * 60 + now.minute
        return open_minutes <= now_minutes < close_minutes

    async def scan_once(self) -> dict:
        await self.refresh_watchlist_if_due()
        watchlist = self.store.get_watchlist()
        if not watchlist:
            self.store.seed_watchlist(self.settings.watchlist)
            watchlist = self.store.get_watchlist()

        scan_stats = {"symbols": len(watchlist), "signals": 0, "entries": 0, "exits": 0}

        # Exit processing — skip polling if WebSocket monitor is handling exits.
        open_positions = {p.symbol: p for p in self.store.get_open_positions()}
        if open_positions and not self.ws_monitor:
            exit_snaps = await self.data_collector.fetch_snapshots(list(open_positions.keys()))
            for symbol, pos in open_positions.items():
                snap = exit_snaps.get(symbol)
                if not snap:
                    logger.warning("No market data for open position %s — exit check skipped", symbol)
                    continue
                should_exit, event = self.tracker.evaluate_exit(pos, snap)
                if should_exit:
                    await self.execution.submit_exit(symbol, pos.qty)
                    self.store.close_position(symbol, status=event)
                    self.cache.should_suppress_signal(symbol)  # prevent re-entry this cycle
                    await self.alerts.send(self.alerts.format_exit(pos, event))
                    scan_stats["exits"] += 1

        open_positions = {p.symbol: p for p in self.store.get_open_positions()}

        # Signal scan — use real-time WS data when available, Polygon fallback.
        if self.ws_data_feed:
            all_snaps: dict = {}
            fallback_symbols = []
            for symbol in watchlist:
                if self.ws_data_feed.has_data(symbol):
                    snap = self.ws_data_feed.get_snapshot(symbol)
                    if snap:
                        all_snaps[symbol] = snap
                        continue
                fallback_symbols.append(symbol)
            if fallback_symbols:
                polygon_snaps = await self.data_collector.fetch_snapshots(fallback_symbols)
                all_snaps.update({s: v for s, v in polygon_snaps.items() if v})
            logger.debug("Scan data: %d real-time, %d Polygon fallback",
                         len(watchlist) - len(fallback_symbols), len(fallback_symbols))
        else:
            all_snaps = await self.data_collector.fetch_snapshots(watchlist)

        # Patch avg_daily_volume from universe selector data so the liquidity
        # filter works even when Finnhub WS/Quote lacks volume info.
        for symbol, snap in all_snaps.items():
            cached_vol = self._daily_volumes.get(symbol)
            if cached_vol and cached_vol > snap.avg_daily_volume:
                snap.avg_daily_volume = cached_vol

        for symbol in watchlist:
            snap = all_snaps.get(symbol)
            if snap is None:
                continue
            self.store.save_snapshot(snap)

            if symbol in open_positions:
                continue

            signal = self.signal_engine.evaluate(snap)
            approved_risk, risk_note = self.risk_manager.approve(signal, len(open_positions))
            approved_ai, ai_note = self.ai_review.review(signal)

            final_approved = approved_risk and approved_ai
            merged_note = f"{risk_note}; {ai_note}"
            if not final_approved:
                logger.info(
                    "Signal rejected for %s: side=%s reason=%r | risk=%s ai=%s",
                    symbol, signal.side.value, signal.reason, risk_note, ai_note,
                )
            self.store.save_signal(signal, final_approved, merged_note)
            scan_stats["signals"] += 1

            if not final_approved:
                continue
            if self.cache.should_suppress_signal(symbol):
                logger.info("Suppressed duplicate signal for %s", symbol)
                continue

            qty = self.risk_manager.calculate_qty(signal)
            order = await self.execution.submit_entry(signal, qty=qty)
            self.store.log_order(symbol, signal.side.value, qty, "market", order.status, order.broker_order_id)
            if order.status in {"SUBMITTED", "PAPER_SIMULATED"}:
                pos = Position(
                    symbol=symbol,
                    side=signal.side,
                    qty=qty,
                    entry=signal.entry,
                    stop_loss=signal.stop_loss,
                    target=signal.target,
                    opened_at=datetime.utcnow(),
                    status="OPEN",
                    broker_order_id=order.broker_order_id,
                    pattern=signal.pattern.value,
                    confidence=signal.confidence,
                    entry_vwap=snap.vwap,
                    entry_premarket_high=snap.premarket_high,
                    entry_trend_score=snap.trend_score,
                    entry_momentum_score=snap.momentum_score,
                    entry_relative_volume=snap.relative_volume,
                    entry_reason=signal.reason,
                )
                self.store.open_position(pos)
                await self.alerts.send(self.alerts.format_signal(signal, merged_note))
                if self.ws_monitor:
                    await self.ws_monitor.notify_position_opened(symbol)
                scan_stats["entries"] += 1

        self.cache.set_json("runtime:last_scan", {"ts": datetime.utcnow().isoformat(), **scan_stats}, ttl_sec=3600)
        return scan_stats

    async def refresh_watchlist_if_due(self, force: bool = False) -> None:
        now = datetime.utcnow()
        refresh_every = timedelta(minutes=max(self.settings.watchlist_refresh_minutes, 1))
        due = force or self._last_watchlist_refresh is None or (now - self._last_watchlist_refresh) >= refresh_every
        if not due:
            return

        candidates = await self.universe_selector.build_watchlist()
        if candidates:
            self.store.replace_watchlist(candidates)
            self._daily_volumes = dict(self.universe_selector.daily_volumes)
            self._last_watchlist_refresh = now
            if self.ws_data_feed:
                await self.ws_data_feed.update_subscriptions(candidates)
            logger.info("Watchlist refreshed with %s symbols", len(candidates))

    async def run_forever(self) -> None:
        watchlist_ready = False
        daily_cleared = False
        while True:
            loop_start = time.monotonic()
            try:
                if self.market_is_open():
                    daily_cleared = False
                    if not watchlist_ready:
                        await self.refresh_watchlist_if_due(force=True)
                        watchlist_ready = True
                        logger.info("Initial watchlist refresh done, scanning starts next cycle")
                    else:
                        stats = await self.scan_once()
                        elapsed = time.monotonic() - loop_start
                        logger.info("Scan complete (%.1fs): %s", elapsed, stats)
                else:
                    if not daily_cleared:
                        self.store.clear_daily_data()
                        if self.ws_data_feed:
                            self.ws_data_feed.clear_day()
                        logger.info("Market closed — daily data cleared")
                        daily_cleared = True
                    watchlist_ready = False
                    logger.info("Market closed, sleeping")
            except Exception as exc:
                logger.exception("Scan loop error: %s", exc)
            elapsed = time.monotonic() - loop_start
            await asyncio.sleep(max(self.settings.scan_interval_seconds - elapsed, 1))
