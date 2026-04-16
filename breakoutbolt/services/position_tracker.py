from __future__ import annotations

from breakoutbolt.models import Position, SignalSide, SymbolSnapshot


class PositionTracker:
    def evaluate_exit(self, position: Position, snap: SymbolSnapshot) -> tuple[bool, str]:
        if position.side == SignalSide.BUY:
            if snap.bar_low <= position.stop_loss:
                return True, "STOP_LOSS_HIT"
            if snap.bar_high >= position.target:
                return True, "TARGET_HIT"
        return False, "HOLD"
