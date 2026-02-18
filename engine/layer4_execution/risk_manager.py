"""
CryptoAI Master — 리스크 매니저
==============================

손절(-3%) / 익절(+5%) 자동 실행 + 트레일링 스탑 + 최대 손실 한도.

Usage:
    >>> risk = RiskManager(settings=settings)
    >>> actions = risk.check_positions(positions, current_prices)
    >>> for a in actions:
    ...     if a.action != "HOLD":
    ...         order_manager.execute_sell(a.symbol, ...)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskAction:
    """리스크 체크 결과 액션.

    Attributes:
        symbol: 코인 심볼.
        action: "HOLD", "STOP_LOSS", "TAKE_PROFIT", "TRAILING_STOP", "MAX_HOLD".
        pnl_pct: 현재 손익률 (%).
        pnl_krw: 현재 손익 금액 (KRW).
        reason: 설명.
        urgency: 긴급도 (1=정상, 2=주의, 3=즉시).
    """
    symbol: str
    action: str
    pnl_pct: float
    pnl_krw: float
    reason: str
    urgency: int = 1

    @property
    def emoji(self) -> str:
        """액션 이모지."""
        return {
            "HOLD": "🟢",
            "STOP_LOSS": "🔴",
            "TAKE_PROFIT": "💰",
            "TRAILING_STOP": "📉",
            "MAX_HOLD": "⏰",
        }.get(self.action, "⚪")

    def __str__(self) -> str:
        return (
            f"{self.emoji} [{self.symbol}] {self.action} | "
            f"PnL: {self.pnl_pct:+.2f}% (₩{self.pnl_krw:+,.0f}) | "
            f"{self.reason}"
        )


class RiskManager:
    """리스크 관리 엔진.

    포지션별 손절/익절/트레일링 스탑/최대 보유 기간을 체크합니다.

    Args:
        stop_loss_pct: 손절 기준 (%, 음수). 기본값 -3.0.
        take_profit_pct: 익절 기준 (%, 양수). 기본값 5.0.
        trailing_stop_pct: 고점 대비 트레일링 스탑 (%). 기본값 2.0.
        max_hold_hours: 최대 보유 시간. 기본값 72.
        daily_loss_limit_pct: 일일 최대 손실 한도 (%). 기본값 -5.0.

    Example:
        >>> risk = RiskManager(stop_loss_pct=-3, take_profit_pct=5)
        >>> actions = risk.check_positions(positions, prices)
    """

    def __init__(
        self,
        stop_loss_pct: float = -3.0,
        take_profit_pct: float = 5.0,
        trailing_stop_pct: float = 2.0,
        max_hold_hours: int = 72,
        daily_loss_limit_pct: float = -5.0,
    ) -> None:
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_hold_hours = max_hold_hours
        self.daily_loss_limit_pct = daily_loss_limit_pct

        logger.info(
            "RiskManager 초기화 | 손절=%.1f%% | 익절=+%.1f%% | "
            "트레일링=%.1f%% | 최대보유=%dh",
            stop_loss_pct, take_profit_pct,
            trailing_stop_pct, max_hold_hours,
        )

    def check_positions(
        self,
        positions: List[Dict[str, Any]],
        current_prices: Dict[str, float],
    ) -> List[RiskAction]:
        """모든 오픈 포지션의 리스크를 체크합니다.

        Args:
            positions: 오픈 포지션 리스트.
                각 포지션은 다음 키를 포함:
                - symbol: str
                - avg_buy_price: float
                - volume: float
                - opened_at: datetime 또는 ISO 문자열
                - highest_price: float (옵션, 트레일링 스탑용)
            current_prices: {symbol: 현재가} 딕셔너리.

        Returns:
            RiskAction 리스트 (HOLD 포함).
        """
        actions: List[RiskAction] = []

        for pos in positions:
            symbol = pos["symbol"]
            current_price = current_prices.get(symbol)

            if not current_price:
                logger.warning("[리스크] 현재가 없음: %s", symbol)
                continue

            action = self._evaluate_position(pos, current_price)
            actions.append(action)

            if action.action != "HOLD":
                logger.warning("[리스크 발동] %s", action)

        return actions

    def _evaluate_position(
        self, pos: Dict[str, Any], current_price: float
    ) -> RiskAction:
        """단일 포지션을 평가합니다.

        Args:
            pos: 포지션 딕셔너리.
            current_price: 현재가.

        Returns:
            RiskAction.
        """
        symbol = pos["symbol"]
        avg_price = float(pos["avg_buy_price"])
        volume = float(pos["volume"])

        # PnL 계산
        if avg_price <= 0:
            return RiskAction(
                symbol=symbol, action="HOLD",
                pnl_pct=0, pnl_krw=0,
                reason="매입가 정보 없음",
            )

        pnl_pct = (current_price - avg_price) / avg_price * 100
        pnl_krw = (current_price - avg_price) * volume

        # ── 1. 손절 체크 (최우선) ──
        if pnl_pct <= self.stop_loss_pct:
            return RiskAction(
                symbol=symbol,
                action="STOP_LOSS",
                pnl_pct=pnl_pct,
                pnl_krw=pnl_krw,
                reason=f"손절 발동: {pnl_pct:.2f}% ≤ {self.stop_loss_pct}%",
                urgency=3,
            )

        # ── 2. 익절 체크 ──
        if pnl_pct >= self.take_profit_pct:
            return RiskAction(
                symbol=symbol,
                action="TAKE_PROFIT",
                pnl_pct=pnl_pct,
                pnl_krw=pnl_krw,
                reason=f"익절 발동: {pnl_pct:.2f}% ≥ +{self.take_profit_pct}%",
                urgency=2,
            )

        # ── 3. 트레일링 스탑 체크 ──
        highest = float(pos.get("highest_price", current_price))
        if highest > avg_price:
            drop_from_high = (highest - current_price) / highest * 100
            if drop_from_high >= self.trailing_stop_pct and pnl_pct > 0:
                return RiskAction(
                    symbol=symbol,
                    action="TRAILING_STOP",
                    pnl_pct=pnl_pct,
                    pnl_krw=pnl_krw,
                    reason=(
                        f"트레일링 스탑: 고점 ₩{highest:,.0f} 대비 "
                        f"-{drop_from_high:.2f}% 하락"
                    ),
                    urgency=2,
                )

        # ── 4. 최대 보유 기간 체크 ──
        opened_at = pos.get("opened_at")
        if opened_at:
            if isinstance(opened_at, str):
                try:
                    opened_at = datetime.fromisoformat(opened_at)
                except ValueError:
                    opened_at = None

            if opened_at and (datetime.now() - opened_at) > timedelta(hours=self.max_hold_hours):
                return RiskAction(
                    symbol=symbol,
                    action="MAX_HOLD",
                    pnl_pct=pnl_pct,
                    pnl_krw=pnl_krw,
                    reason=f"최대 보유 기간 초과: {self.max_hold_hours}시간",
                    urgency=1,
                )

        # ── 5. 홀드 ──
        return RiskAction(
            symbol=symbol,
            action="HOLD",
            pnl_pct=pnl_pct,
            pnl_krw=pnl_krw,
            reason=f"정상 범위 (손절 {self.stop_loss_pct}% ~ 익절 +{self.take_profit_pct}%)",
        )

    def check_daily_loss(
        self,
        daily_pnl_krw: float,
        total_portfolio_krw: float,
    ) -> bool:
        """일일 최대 손실 한도를 초과했는지 확인합니다.

        Args:
            daily_pnl_krw: 오늘 총 손익 (KRW).
            total_portfolio_krw: 전체 포트폴리오 가치.

        Returns:
            True면 거래 중단. False면 계속.
        """
        if total_portfolio_krw <= 0:
            return False

        daily_pnl_pct = daily_pnl_krw / total_portfolio_krw * 100

        if daily_pnl_pct <= self.daily_loss_limit_pct:
            logger.critical(
                "🚨 일일 최대 손실 한도 도달! "
                "PnL=₩%s (%.2f%%) ≤ %.1f%% → 거래 중단",
                f"{daily_pnl_krw:,.0f}", daily_pnl_pct,
                self.daily_loss_limit_pct,
            )
            return True

        return False
