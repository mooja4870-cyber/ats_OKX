"""
CryptoAI Master — 코인 유니버스 설정
====================================

자동매매 대상 코인과 관련 메타데이터를 관리합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class CoinInfo:
    """코인 메타데이터.

    Attributes:
        symbol: 코인 심볼 (예: "BTC")
        name: 코인 전체 이름
        upbit_ticker: 업비트 티커 (예: "KRW-BTC")
        emoji: 대시보드 표시용 이모지
        color: 차트 컬러 (hex)
        min_order_krw: 최소 주문 금액 (KRW)
    """
    symbol: str
    name: str
    upbit_ticker: str
    emoji: str
    color: str
    min_order_krw: int = 5_000  # 업비트 최소 주문 금액


# ─── 대상 코인 정의 ───

COIN_UNIVERSE: Dict[str, CoinInfo] = {
    "BTC": CoinInfo(
        symbol="BTC",
        name="Bitcoin",
        upbit_ticker="KRW-BTC",
        emoji="🪙",
        color="#F7931A",
    ),
    "ETH": CoinInfo(
        symbol="ETH",
        name="Ethereum",
        upbit_ticker="KRW-ETH",
        emoji="💠",
        color="#627EEA",
    ),
    "XRP": CoinInfo(
        symbol="XRP",
        name="XRP",
        upbit_ticker="KRW-XRP",
        emoji="🌊",
        color="#00AAE4",
    ),
    "SOL": CoinInfo(
        symbol="SOL",
        name="Solana",
        upbit_ticker="KRW-SOL",
        emoji="☀️",
        color="#9945FF",
    ),
}

# ─── 유틸리티 ───

DEFAULT_COINS: List[str] = list(COIN_UNIVERSE.keys())


def get_coin(symbol: str) -> CoinInfo:
    """심볼로 코인 정보를 반환합니다.

    Args:
        symbol: 코인 심볼 (대소문자 무관).

    Returns:
        CoinInfo 객체.

    Raises:
        KeyError: 정의되지 않은 코인 심볼.
    """
    key = symbol.upper()
    if key not in COIN_UNIVERSE:
        raise KeyError(
            f"지원하지 않는 코인: {symbol}. "
            f"지원 코인: {', '.join(DEFAULT_COINS)}"
        )
    return COIN_UNIVERSE[key]


def get_upbit_ticker(symbol: str) -> str:
    """심볼을 업비트 티커로 변환합니다.

    Args:
        symbol: 코인 심볼 (예: "BTC")

    Returns:
        업비트 티커 (예: "KRW-BTC")
    """
    return get_coin(symbol).upbit_ticker
