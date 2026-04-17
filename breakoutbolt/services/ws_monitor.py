from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import websockets

from breakoutbolt.db.sqlite_store import SQLiteStore
from breakoutbolt.models import Position, SignalSide
from breakoutbolt.services.alert_dispatcher import AlertDispatcher
from breakoutbolt.services.state_cache import StateCache

if TYPE_CHECKING:
    from breakoutbolt.services.execution import OrderExecutionService

logger = logging.getLogger(__name__)

WS_URL = "wss://stream.data.alpaca.markets/v2/iex"


class WebSocketExitMonitor:
    """Streams real-time IEX trades from Alpaca and triggers exits on stop/target hits."""

    def __init__(
        self,
        alpaca_api_key: str,
        alpaca_api_secret: str,
        store: SQLiteStore,
        alerts: AlertDispatcher,
        cache: StateCache,
        execution: OrderExecutionService | None = None,
    ) -> None:
        self.api_key = alpaca_api_key
        self.api_secret = alpaca_api_secret
        self.store = store
        self.alerts = alerts
        self.cache = cache
        self.execution = execution
        self._positions: dict[str, Position] = {}
        self._ws = None
        self._subscribed: set[str] = set()

    async def run_forever(self) -> None:
        """Connect, authenticate, and stream trades. Reconnects on failure."""
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    self._ws = ws
                    await self._authenticate(ws)
                    # Sync subscriptions with current open positions.
                    await self._sync_subscriptions()
                    logger.info("WebSocket exit monitor connected and authenticated")
                    async for raw in ws:
                        await self._handle_message(raw)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as exc:
                logger.warning("WebSocket disconnected: %s — reconnecting in 5s", exc)
            except Exception as exc:
                logger.exception("WebSocket monitor error: %s", exc)
            self._ws = None
            self._subscribed.clear()
            await asyncio.sleep(5)

    async def _authenticate(self, ws) -> None:
        # Read the welcome message.
        welcome = await ws.recv()
        logger.debug("WS welcome: %s", welcome)
        auth_msg = json.dumps({"action": "auth", "key": self.api_key, "secret": self.api_secret})
        await ws.send(auth_msg)
        resp = await ws.recv()
        data = json.loads(resp)
        if isinstance(data, list):
            for msg in data:
                if msg.get("T") == "error":
                    raise ConnectionError(f"Alpaca WS auth failed: {msg}")
        logger.debug("WS auth response: %s", resp)

    async def _sync_subscriptions(self) -> None:
        """Subscribe to trades for all currently open positions."""
        self._positions = {p.symbol: p for p in self.store.get_open_positions()}
        needed = set(self._positions.keys())
        to_sub = needed - self._subscribed
        to_unsub = self._subscribed - needed
        if to_unsub and self._ws:
            await self._ws.send(json.dumps({"action": "unsubscribe", "trades": list(to_unsub)}))
            self._subscribed -= to_unsub
        if to_sub and self._ws:
            await self._ws.send(json.dumps({"action": "subscribe", "trades": list(to_sub)}))
            self._subscribed |= to_sub
        if to_sub or to_unsub:
            logger.info("WS subscriptions updated: +%s -%s (active: %s)", to_sub, to_unsub, self._subscribed)

    async def _handle_message(self, raw: str) -> None:
        messages = json.loads(raw)
        if not isinstance(messages, list):
            return
        for msg in messages:
            msg_type = msg.get("T")
            if msg_type == "t":  # trade
                await self._on_trade(msg)
            elif msg_type == "subscription":
                logger.debug("WS subscription confirmed: %s", msg)
            elif msg_type == "error":
                logger.error("WS error: %s", msg)

    async def _on_trade(self, trade: dict) -> None:
        symbol = trade.get("S")
        price = trade.get("p")
        if not symbol or price is None:
            return
        pos = self._positions.get(symbol)
        if not pos:
            return

        should_exit = False
        event = "HOLD"

        if pos.side == SignalSide.BUY:
            if price <= pos.stop_loss:
                should_exit = True
                event = "STOP_LOSS_HIT"
            elif price >= pos.target:
                should_exit = True
                event = "TARGET_HIT"

        if should_exit:
            logger.info("WS exit triggered: %s %s at %.2f (entry=%.2f stop=%.2f target=%.2f)",
                        event, symbol, price, pos.entry, pos.stop_loss, pos.target)
            # Submit sell order to broker before updating DB.
            if self.execution:
                await self.execution.submit_exit(symbol, pos.qty)
            self.store.close_position(symbol, status=event, exit_price=price)
            self.cache.should_suppress_signal(symbol)
            await self.alerts.send(self.alerts.format_exit(pos, event))
            # Remove from local tracking and unsubscribe.
            self._positions.pop(symbol, None)
            if self._ws:
                await self._ws.send(json.dumps({"action": "unsubscribe", "trades": [symbol]}))
                self._subscribed.discard(symbol)

    async def notify_position_opened(self, symbol: str) -> None:
        """Called by orchestrator when a new position is opened."""
        positions = {p.symbol: p for p in self.store.get_open_positions()}
        self._positions = positions
        if symbol not in self._subscribed and self._ws:
            await self._ws.send(json.dumps({"action": "subscribe", "trades": [symbol]}))
            self._subscribed.add(symbol)
            logger.info("WS subscribed to new position: %s", symbol)

    async def notify_position_closed(self, symbol: str) -> None:
        """Called by orchestrator when a position is closed (by polling)."""
        self._positions.pop(symbol, None)
        if symbol in self._subscribed and self._ws:
            await self._ws.send(json.dumps({"action": "unsubscribe", "trades": [symbol]}))
            self._subscribed.discard(symbol)

    async def periodic_sync(self, interval: int = 60) -> None:
        """Periodically re-sync subscriptions with DB in case of drift."""
        while True:
            await asyncio.sleep(interval)
            try:
                await self._sync_subscriptions()
            except Exception as exc:
                logger.warning("WS periodic sync failed: %s", exc)
