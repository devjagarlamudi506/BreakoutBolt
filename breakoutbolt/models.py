from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SignalSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PatternType(str, Enum):
    BREAKOUT_CONTINUATION = "breakout_continuation"
    PULLBACK_TO_VWAP = "pullback_to_vwap"
    NONE = "none"


@dataclass(slots=True)
class SymbolSnapshot:
    symbol: str
    timestamp: datetime
    last_price: float
    vwap: float
    premarket_high: float
    trend_score: float
    momentum_score: float
    relative_volume: float
    avg_daily_volume: float
    intraday_volume: float

    @property
    def dollar_volume(self) -> float:
        return self.last_price * self.intraday_volume


@dataclass(slots=True)
class TradeSignal:
    symbol: str
    side: SignalSide
    pattern: PatternType
    entry: float
    stop_loss: float
    target: float
    reward_to_risk: float
    confidence: float
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Position:
    symbol: str
    side: SignalSide
    qty: float
    entry: float
    stop_loss: float
    target: float
    opened_at: datetime
    status: str = "OPEN"
    broker_order_id: str | None = None
    pattern: str | None = None
    confidence: float | None = None
    entry_vwap: float | None = None
    entry_premarket_high: float | None = None
    entry_trend_score: float | None = None
    entry_momentum_score: float | None = None
    entry_relative_volume: float | None = None
    entry_reason: str | None = None
