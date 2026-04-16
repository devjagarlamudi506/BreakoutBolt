from __future__ import annotations

from breakoutbolt.models import Position, SignalSide, SymbolSnapshot


class PositionTracker:
    def evaluate_exit(self, position: Position, snap: SymbolSnapshot) -> tuple[bool, str]:
        if position.side == SignalSide.BUY:
            if snap.last_price <= position.stop_loss:
                return True, "STOP_LOSS_HIT"
            if snap.last_price >= position.target:
                return True, "TARGET_HIT"
        return False, "HOLD"
