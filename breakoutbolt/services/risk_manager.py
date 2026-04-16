from __future__ import annotations

from breakoutbolt.config import Settings
from breakoutbolt.models import SignalSide, TradeSignal


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def calculate_qty(self, signal: TradeSignal) -> float:
        """Risk-based position sizing: risk_per_trade / per_share_risk, capped by max_position_value."""
        per_share_risk = abs(signal.entry - signal.stop_loss)
        if per_share_risk < 0.01:
            return 1.0
        qty_by_risk = self.settings.risk_per_trade / per_share_risk
        qty_by_value = self.settings.max_position_value / signal.entry if signal.entry > 0 else 1.0
        qty = min(qty_by_risk, qty_by_value)
        return max(1.0, float(int(qty)))  # whole shares, minimum 1

    def approve(self, signal: TradeSignal, active_positions_count: int) -> tuple[bool, str]:
        if signal.side == SignalSide.HOLD:
            return False, "HOLD signal"
        if signal.entry <= 0 or signal.stop_loss <= 0 or signal.target <= 0:
            return False, "Missing mandatory risk levels"
        if signal.stop_loss >= signal.entry:
            return False, "Invalid stop for long trade"
        if signal.reward_to_risk < self.settings.min_reward_to_risk:
            return False, "Reward-to-risk below threshold"
        if active_positions_count >= self.settings.max_active_positions:
            return False, "Max active positions reached"
        return True, "Risk approved"
