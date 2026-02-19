"""Discord webhook notifier for engine events."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


class DiscordNotifier:
    """Send engine notifications to Discord via webhook."""

    def __init__(self, webhook_url: str, timeout_sec: float = 8.0) -> None:
        self.webhook_url = (webhook_url or "").strip()
        self.timeout_sec = timeout_sec

    def _is_enabled(self) -> bool:
        if not self.webhook_url:
            return False
        return "discord.com/api/webhooks/" in self.webhook_url

    def _post(self, content: str) -> None:
        if not self._is_enabled():
            return
        httpx.post(
            self.webhook_url,
            json={"content": content},
            timeout=self.timeout_sec,
        ).raise_for_status()

    @staticmethod
    def _safe_json(data: Any) -> str:
        if is_dataclass(data):
            data = asdict(data)
        if isinstance(data, dict):
            return ", ".join(f"{k}={v}" for k, v in data.items())
        return str(data)

    def send_trade_alert(self, data: Dict[str, Any]) -> None:
        symbol = data.get("symbol", "-")
        side = data.get("side", "-")
        price = data.get("price", "-")
        qty = data.get("quantity", "-")
        score = data.get("score", "-")
        self._post(
            f"💸 [매매] {side} {symbol} | 가격={price} | 수량={qty} | 점수={score}"
        )

    def send_risk_alert(self, data: Any) -> None:
        self._post(f"🛡️ [리스크] {self._safe_json(data)}")

    def send_scoring_report(self, results: List[Any]) -> None:
        top = results[:4]
        parts = []
        for r in top:
            symbol = getattr(r, "symbol", "?")
            score = round(float(getattr(r, "total_score", 0.0)), 1)
            signal = getattr(r, "signal", "-")
            parts.append(f"{symbol} {score}({signal})")
        self._post("📊 [스코어] " + " | ".join(parts))

    def send_error_alert(self, message: str) -> None:
        self._post(f"🚨 [오류] {message}")

    def send_system_alert(self, message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._post(f"🤖 [시스템] {message} ({ts})")

