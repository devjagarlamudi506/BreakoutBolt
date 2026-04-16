from __future__ import annotations

from datetime import datetime

from breakoutbolt.config import Settings
from breakoutbolt.models import PatternType, SignalSide, SymbolSnapshot, TradeSignal


class SignalEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, snap: SymbolSnapshot) -> TradeSignal:
        if snap.dollar_volume < self.settings.min_dollar_volume:
            return self._hold(snap.symbol, "Liquidity filter failed")
        if snap.relative_volume < self.settings.min_relative_volume:
            return self._hold(snap.symbol, "Relative volume filter failed")

        breakout = self._breakout_continuation(snap)
        pullback = self._pullback_to_vwap(snap)

        if breakout and not pullback:
            return breakout
        if pullback and not breakout:
            return pullback
        if breakout and pullback:
            if breakout.confidence >= pullback.confidence:
                return breakout
            return pullback
        return self._hold(snap.symbol, "No clean pattern")

    def _breakout_continuation(self, s: SymbolSnapshot) -> TradeSignal | None:
        above_vwap = s.last_price > s.vwap
        breaking_high = s.last_price >= s.premarket_high * 0.998
        trend_ok = s.trend_score > 0.008 and s.momentum_score > 0.2
        if not (above_vwap and breaking_high and trend_ok):
            return None

        entry = s.last_price
        stop = min(s.vwap * 0.998, entry * 0.992)
        target = entry + (entry - stop) * 2.4
        rr = (target - entry) / max(entry - stop, 1e-9)
        conf = min(0.95, 0.6 + s.trend_score * 2 + max(0.0, s.momentum_score) * 0.06)
        return TradeSignal(
            symbol=s.symbol,
            side=SignalSide.BUY,
            pattern=PatternType.BREAKOUT_CONTINUATION,
            entry=entry,
            stop_loss=stop,
            target=target,
            reward_to_risk=rr,
            confidence=conf,
            reason="Breakout continuation above VWAP and premarket high",
            timestamp=datetime.utcnow(),
        )

    def _pullback_to_vwap(self, s: SymbolSnapshot) -> TradeSignal | None:
        strong_trend = s.trend_score > 0.01 and s.momentum_score > 0.1
        near_vwap = abs(s.last_price - s.vwap) / max(s.vwap, 1e-9) <= 0.004
        reclaiming = s.last_price >= s.vwap
        if not (strong_trend and near_vwap and reclaiming):
            return None

        entry = s.last_price
        stop = s.vwap * 0.996
        target = entry + (entry - stop) * 2.2
        rr = (target - entry) / max(entry - stop, 1e-9)
        conf = min(0.9, 0.55 + s.trend_score * 1.5 + max(0.0, s.momentum_score) * 0.05)
        return TradeSignal(
            symbol=s.symbol,
            side=SignalSide.BUY,
            pattern=PatternType.PULLBACK_TO_VWAP,
            entry=entry,
            stop_loss=stop,
            target=target,
            reward_to_risk=rr,
            confidence=conf,
            reason="Pullback to VWAP in strong uptrend with momentum persistence",
            timestamp=datetime.utcnow(),
        )

    def _hold(self, symbol: str, reason: str) -> TradeSignal:
        return TradeSignal(
            symbol=symbol,
            side=SignalSide.HOLD,
            pattern=PatternType.NONE,
            entry=0,
            stop_loss=0,
            target=0,
            reward_to_risk=0,
            confidence=0.35,
            reason=reason,
            timestamp=datetime.utcnow(),
        )
