from __future__ import annotations

from breakoutbolt.models import SignalSide, TradeSignal


class AIReviewLayer:
    """Lightweight validator for final shortlist only.

    This is intentionally simple and deterministic-friendly.
    Replace with LLM scoring in production if desired.
    """

    def review(self, signal: TradeSignal) -> tuple[bool, str]:
        if signal.side == SignalSide.HOLD:
            return False, "No setup"
        if signal.confidence < 0.58:
            return False, "Confidence too low"
        if "No clean pattern" in signal.reason:
            return False, "Ambiguous setup"
        return True, "AI validation approved"
