from __future__ import annotations

import json
import logging
import time

import redis

logger = logging.getLogger(__name__)


class StateCache:
    def __init__(self, redis_url: str) -> None:
        self._mem: dict[str, tuple[str, float]] = {}
        self._redis = None
        try:
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
        except Exception:
            logger.warning("Redis unavailable; using in-memory cache fallback")
            self._redis = None

    def set_json(self, key: str, value: dict, ttl_sec: int | None = None) -> None:
        payload = json.dumps(value)
        if self._redis is not None:
            self._redis.set(key, payload, ex=ttl_sec)
            return
        expiry = time.time() + ttl_sec if ttl_sec else float("inf")
        self._mem[key] = (payload, expiry)

    def get_json(self, key: str) -> dict | None:
        if self._redis is not None:
            raw = self._redis.get(key)
            return json.loads(raw) if raw else None
        item = self._mem.get(key)
        if not item:
            return None
        raw, exp = item
        if exp < time.time():
            self._mem.pop(key, None)
            return None
        return json.loads(raw)

    def should_suppress_signal(self, symbol: str, minutes: int = 15) -> bool:
        key = f"signal_lock:{symbol}"
        existing = self.get_json(key)
        if existing:
            return True
        self.set_json(key, {"symbol": symbol, "ts": int(time.time())}, ttl_sec=minutes * 60)
        return False

    def suppress_buy_signal(self, symbol: str, pattern: str, minutes: int = 5) -> bool:
        """Suppress duplicate BUY signals for the same symbol+pattern within a window.

        Returns True if the signal should be suppressed (already seen recently).
        """
        key = f"buy_dedup:{symbol}:{pattern}"
        existing = self.get_json(key)
        if existing:
            return True
        self.set_json(key, {"symbol": symbol, "pattern": pattern, "ts": int(time.time())}, ttl_sec=minutes * 60)
        return False
