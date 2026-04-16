from __future__ import annotations

import logging

import httpx

from breakoutbolt.models import Position, TradeSignal

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def format_signal(self, signal: TradeSignal, ai_note: str) -> dict:
        return {
            "username": "BreakoutBolt",
            "embeds": [
                {
                    "title": f"{signal.side.value} {signal.symbol}",
                    "description": signal.reason,
                    "color": 5763719 if signal.side.value == "BUY" else 9807270,
                    "fields": [
                        {"name": "Entry", "value": f"{signal.entry:.2f}", "inline": True},
                        {"name": "Stop", "value": f"{signal.stop_loss:.2f}", "inline": True},
                        {"name": "Target", "value": f"{signal.target:.2f}", "inline": True},
                        {"name": "R/R", "value": f"{signal.reward_to_risk:.2f}", "inline": True},
                        {"name": "Confidence", "value": f"{signal.confidence:.2%}", "inline": True},
                        {"name": "AI Review", "value": ai_note, "inline": False},
                    ],
                }
            ],
        }

    def format_exit(self, position: Position, event: str) -> dict:
        return {
            "username": "BreakoutBolt",
            "embeds": [
                {
                    "title": f"EXIT {position.symbol}",
                    "description": event,
                    "color": 15158332,
                    "fields": [
                        {"name": "Entry", "value": f"{position.entry:.2f}", "inline": True},
                        {"name": "Stop", "value": f"{position.stop_loss:.2f}", "inline": True},
                        {"name": "Target", "value": f"{position.target:.2f}", "inline": True},
                    ],
                }
            ],
        }

    def format_status(self, watchlist: list[str], positions: list[Position]) -> dict:
        position_lines = [
            f"{p.symbol} | {p.side.value} | entry {p.entry:.2f} | stop {p.stop_loss:.2f} | target {p.target:.2f}"
            for p in positions
        ]
        return {
            "username": "BreakoutBolt",
            "embeds": [
                {
                    "title": "BreakoutBolt Status",
                    "description": "Watchlist and active positions",
                    "color": 3447003,
                    "fields": [
                        {
                            "name": "Watchlist",
                            "value": ", ".join(watchlist) if watchlist else "(empty)",
                            "inline": False,
                        },
                        {
                            "name": "Active Positions",
                            "value": "\n".join(position_lines) if position_lines else "No active positions",
                            "inline": False,
                        },
                    ],
                }
            ],
        }

    async def send(self, payload: dict) -> None:
        if not self.webhook_url:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Discord dispatch failed: %s", exc)
