from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
except Exception:  # pragma: no cover
    TradingClient = None
    MarketOrderRequest = None
    OrderSide = None
    TimeInForce = None

from breakoutbolt.config import Settings
from breakoutbolt.models import SignalSide, TradeSignal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OrderResult:
    status: str
    broker_order_id: str | None


class OrderExecutionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = None
        if settings.alpaca_api_key and settings.alpaca_api_secret and TradingClient is not None:
            self.client = TradingClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_api_secret,
                paper=settings.alpaca_paper,
            )

    async def submit_entry(self, signal: TradeSignal, qty: float = 1.0) -> OrderResult:
        if signal.side != SignalSide.BUY:
            return OrderResult(status="SKIPPED", broker_order_id=None)

        # Safe default: no live orders unless explicitly enabled.
        if not self.settings.alpaca_live_enabled:
            return OrderResult(status="PAPER_SIMULATED", broker_order_id=f"sim-{signal.symbol}")

        if self.client is None:
            logger.warning("Alpaca client unavailable; falling back to simulation")
            return OrderResult(status="PAPER_SIMULATED", broker_order_id=f"sim-{signal.symbol}")

        try:
            req = MarketOrderRequest(
                symbol=signal.symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            order = await asyncio.to_thread(self.client.submit_order, order_data=req)
            return OrderResult(status="SUBMITTED", broker_order_id=str(order.id))
        except Exception as exc:
            logger.exception("Order submission failed: %s", exc)
            return OrderResult(status="FAILED", broker_order_id=None)

    async def submit_exit(self, symbol: str, qty: float) -> OrderResult:
        """Submit a market sell order to close a position."""
        if not self.settings.alpaca_live_enabled:
            return OrderResult(status="PAPER_SIMULATED", broker_order_id=f"sim-exit-{symbol}")

        if self.client is None:
            logger.warning("Alpaca client unavailable; falling back to simulation for exit")
            return OrderResult(status="PAPER_SIMULATED", broker_order_id=f"sim-exit-{symbol}")

        try:
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = await asyncio.to_thread(self.client.submit_order, order_data=req)
            logger.info("Exit order submitted for %s qty=%.0f order_id=%s", symbol, qty, order.id)
            return OrderResult(status="SUBMITTED", broker_order_id=str(order.id))
        except Exception as exc:
            logger.exception("Exit order failed for %s: %s", symbol, exc)
            return OrderResult(status="FAILED", broker_order_id=None)
