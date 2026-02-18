"""
CryptoAI Master — 포트폴리오 배분기
====================================

스코어링 결과를 기반으로 매수 예산을 코인별로 최적 배분합니다.

전략:
    - 점수 비례 배분 (고점수 코인에 더 많은 예산)
    - 최소/최대 배분 비율 제한
    - STRONG_BUY는 배분 비율 1.5배 부스트
    - 최소 주문 금액(₩5,000) 미달 시 배분 제외

Usage:
    >>> allocator = PortfolioAllocator(total_budget=700_000)
    >>> allocations = allocator.allocate(candidates, current_prices)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Allocation:
    """포트폴리오 배분 결과.

    Attributes:
        symbol: 코인 심볼.
        score: AI 스코어.
        signal: 시그널 (BUY / STRONG_BUY).
        weight: 배분 가중치 (0-1).
        allocation_amount: 배분 금액 (KRW).
        limit_price: 지정가 (현재가 -0.3%).
        target_quantity: 매수 목표 수량.
    """
    symbol: str
    score: float
    signal: str
    weight: float
    allocation_amount: float
    limit_price: float
    target_quantity: float

    def __str__(self) -> str:
        return (
            f"[{self.symbol}] ₩{self.allocation_amount:>10,.0f} "
            f"({self.weight:.1%}) | "
            f"{self.target_quantity:.8f}개 @ ₩{self.limit_price:,.0f} "
            f"| {self.signal} ({self.score:.0f}점)"
        )


class PortfolioAllocator:
    """스코어 기반 포트폴리오 배분기.

    Args:
        min_allocation_pct: 코인당 최소 배분 비율. 기본 10%.
        max_allocation_pct: 코인당 최대 배분 비율. 기본 50%.
        strong_buy_boost: STRONG_BUY 가중치 부스트. 기본 1.5배.
        limit_discount_pct: 지정가 할인율. 기본 0.3% (현재가 대비).
        min_order_krw: 최소 주문 금액 (KRW). 기본 5,000.
        reserve_ratio: 예비 자금 비율. 기본 10%.

    Example:
        >>> allocator = PortfolioAllocator()
        >>> allocations = allocator.allocate(700_000, candidates, prices)
    """

    def __init__(
        self,
        min_allocation_pct: float = 0.10,
        max_allocation_pct: float = 0.50,
        strong_buy_boost: float = 1.5,
        limit_discount_pct: float = 0.003,
        min_order_krw: float = 5_000,
        reserve_ratio: float = 0.10,
    ) -> None:
        self.min_allocation_pct = min_allocation_pct
        self.max_allocation_pct = max_allocation_pct
        self.strong_buy_boost = strong_buy_boost
        self.limit_discount_pct = limit_discount_pct
        self.min_order_krw = min_order_krw
        self.reserve_ratio = reserve_ratio

        logger.info(
            "PortfolioAllocator 초기화 | 최소=%.0f%% | 최대=%.0f%% | "
            "STRONG_BUY 부스트=%.1fx | 예비금=%.0f%%",
            min_allocation_pct * 100, max_allocation_pct * 100,
            strong_buy_boost, reserve_ratio * 100,
        )

    def allocate(
        self,
        available_krw: float,
        candidates: List[Any],
        current_prices: Dict[str, float],
    ) -> List[Allocation]:
        """매수 후보에 예산을 배분합니다.

        Args:
            available_krw: 사용 가능한 총 KRW.
            candidates: ScoringResult 리스트 (signal이 BUY/STRONG_BUY인 것만).
            current_prices: {symbol: 현재가} 딕셔너리.

        Returns:
            Allocation 리스트 (배분 금액 내림차순).
        """
        if not candidates:
            logger.info("[배분] 매수 후보 없음")
            return []

        # 예비 자금 차감
        investable = available_krw * (1.0 - self.reserve_ratio)
        logger.info(
            "[배분] 가용=₩%s | 예비금=%.0f%% | 투자가능=₩%s | 후보=%d개",
            f"{available_krw:,.0f}", self.reserve_ratio * 100,
            f"{investable:,.0f}", len(candidates),
        )

        if investable < self.min_order_krw:
            logger.warning("[배분] 투자 가능 금액 부족: ₩%s", f"{investable:,.0f}")
            return []

        # 1. 점수 기반 가중치 계산
        raw_weights: Dict[str, float] = {}
        for c in candidates:
            symbol = c.symbol
            if symbol not in current_prices:
                logger.warning("[배분] 현재가 없음: %s (건너뜀)", symbol)
                continue

            weight = c.total_score
            if c.signal == "STRONG_BUY":
                weight *= self.strong_buy_boost

            raw_weights[symbol] = weight

        if not raw_weights:
            return []

        # 2. 정규화
        total_weight = sum(raw_weights.values())
        normalized: Dict[str, float] = {
            s: w / total_weight for s, w in raw_weights.items()
        }

        # 3. 최소/최대 비율 클램핑
        clamped: Dict[str, float] = {}
        for symbol, w in normalized.items():
            clamped[symbol] = max(self.min_allocation_pct,
                                   min(self.max_allocation_pct, w))

        # 재정규화
        clamped_total = sum(clamped.values())
        if clamped_total > 0:
            clamped = {s: w / clamped_total for s, w in clamped.items()}

        # 4. 금액 배분
        allocations: List[Allocation] = []
        for c in candidates:
            symbol = c.symbol
            if symbol not in clamped:
                continue

            weight = clamped[symbol]
            amount = investable * weight

            # 최소 주문 금액 체크
            if amount < self.min_order_krw:
                logger.info(
                    "[배분] %s 최소 금액 미달 (₩%s < ₩%s) → 제외",
                    symbol, f"{amount:,.0f}", f"{self.min_order_krw:,.0f}",
                )
                continue

            # 지정가 = 현재가 × (1 - 할인율)
            current_price = current_prices[symbol]
            limit_price = current_price * (1 - self.limit_discount_pct)
            target_qty = amount / limit_price

            allocations.append(Allocation(
                symbol=symbol,
                score=c.total_score,
                signal=c.signal,
                weight=weight,
                allocation_amount=round(amount),
                limit_price=round(limit_price),
                target_quantity=target_qty,
            ))

        # 금액 내림차순 정렬
        allocations.sort(key=lambda a: a.allocation_amount, reverse=True)

        for alloc in allocations:
            logger.info("[배분 결과] %s", alloc)

        return allocations
