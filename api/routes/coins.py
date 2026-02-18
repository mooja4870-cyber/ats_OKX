"""
코인 스코어링 API — /api/coins/*

■ 엔드포인트:
    GET /api/coins/scores          → 전체 코인 AI 점수 (프론트 핵심 API)
    GET /api/coins/scores/{symbol} → 단일 코인 상세 점수
    GET /api/coins/prices/{symbol} → 현재가 (업비트 실시간)
    GET /api/coins/prices          → 전체 코인 현재가 일괄 조회
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger("cryptoai.api.coins")

router = APIRouter()


# ════════════════════════════════════════════════════
# Pydantic 스키마
# ════════════════════════════════════════════════════

class CoinScoreResponse(BaseModel):
    """AI 스코어링 결과 응답 스키마"""

    symbol: str = Field(..., description="코인 심볼 (BTC, ETH 등)", examples=["BTC"])
    name: str = Field("", description="코인 한글/영문명", examples=["Bitcoin"])
    current_price: Optional[float] = Field(None, description="현재가 (KRW)", examples=[143250000])
    price_change_24h: Optional[float] = Field(None, description="24시간 변동률 (%)", examples=[3.52])

    # 5팩터 점수 (0-100)
    technical_score: float = Field(..., ge=0, le=100, description="기술적 분석 점수")
    momentum_score: float = Field(..., ge=0, le=100, description="모멘텀 점수")
    volatility_score: float = Field(..., ge=0, le=100, description="변동성 점수")
    volume_score: float = Field(..., ge=0, le=100, description="거래량 점수")
    sentiment_score: float = Field(..., ge=0, le=100, description="심리 점수")

    # 종합
    total_score: float = Field(..., ge=0, le=100, description="AI 종합 점수")
    signal: str = Field(
        ...,
        description="매매 시그널",
        examples=["STRONG_BUY"],
        pattern="^(STRONG_BUY|BUY|HOLD|SELL)$",
    )
    confidence: float = Field(..., ge=0, le=100, description="AI 신뢰도 (%)")
    reasoning: str = Field(..., description="AI 판단 근거", examples=["RSI 과매도 구간 탈출"])

    # 메타
    scored_at: Optional[str] = Field(None, description="스코어링 시각 (ISO)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "BTC",
                    "name": "Bitcoin",
                    "current_price": 143250000,
                    "price_change_24h": 3.52,
                    "technical_score": 85,
                    "momentum_score": 91,
                    "volatility_score": 72,
                    "volume_score": 88,
                    "sentiment_score": 65,
                    "total_score": 82.3,
                    "signal": "STRONG_BUY",
                    "confidence": 78,
                    "reasoning": "RSI 과매도 구간 탈출 + MACD 골든크로스 발생",
                    "scored_at": "2026-02-18T23:30:00",
                }
            ]
        }
    }


class PriceResponse(BaseModel):
    """현재가 응답 스키마"""

    symbol: str = Field(..., description="코인 심볼")
    market: str = Field(..., description="마켓 코드", examples=["KRW-BTC"])
    price: float = Field(..., description="현재가 (KRW)")
    timestamp: str = Field(..., description="조회 시각 (ISO)")


class BatchPriceResponse(BaseModel):
    """일괄 현재가 응답"""

    prices: List[PriceResponse]
    count: int


# ════════════════════════════════════════════════════
# Mock 데이터 생성 (DB 연동 전 폴백)
# ════════════════════════════════════════════════════

import random


def _rand(mn: int, mx: int) -> int:
    return random.randint(mn, mx)


def _determine_signal(score: float) -> str:
    if score >= 80:
        return "STRONG_BUY"
    if score >= 65:
        return "BUY"
    if score >= 35:
        return "HOLD"
    return "SELL"


_COIN_POOL = [
    {
        "symbol": "BTC",
        "name": "Bitcoin",
        "base_price": 100_000_000,
        "price_range": 2_000_000,
        "score_range": (65, 95),
        "reasonings": [
            "RSI 과매도 구간 탈출 + MACD 골든크로스 발생. 상승 모멘텀이 강합니다.",
            "거래량 폭증과 함께 주요 저항선 돌파. 기관 매수세 유입 중.",
            "Fear & Greed 지수 73 (Greed). 단기 과열 주의하나 추세는 상승.",
            "20일선 지지 확인. 볼린저 밴드 상단 확장 진행 중.",
        ],
    },
    {
        "symbol": "ETH",
        "name": "Ethereum",
        "base_price": 3_900_000,
        "price_range": 150_000,
        "score_range": (50, 80),
        "reasonings": [
            "볼린저 밴드 하단 근접. 단기 반등 가능성이 높습니다.",
            "ETH/BTC 비율 개선. DeFi TVL 증가와 함께 펀더멘탈 강화.",
            "Layer 2 생태계 확장으로 기본 수요 증가. 중기 상승 전망.",
            "Staking 비율 상승 중. 공급 압박으로 가격 지지력 강화.",
        ],
    },
    {
        "symbol": "XRP",
        "name": "Ripple",
        "base_price": 850,
        "price_range": 50,
        "score_range": (30, 60),
        "reasonings": [
            "횡보 구간 지속. 지지선 ₩800 유지 시 반등 가능.",
            "SEC 소송 진행에 따라 변동성 확대 가능. 중립 유지.",
            "거래량 감소 추세. 뚜렷한 방향성 부재로 관망 추천.",
            "일본/아시아 권역 리플넷 활용 증가. 장기 호재 반영 부족.",
        ],
    },
    {
        "symbol": "SOL",
        "name": "Solana",
        "base_price": 220_000,
        "price_range": 10_000,
        "score_range": (55, 85),
        "reasonings": [
            "DeFi TVL 증가세와 함께 기술적 지표 개선. 단기 상승 기대.",
            "NFT/게임 생태계 확장. 네트워크 활용도 역대 최고치 경신.",
            "Jupiter DEX 거래량 급증. Solana 생태계 유동성 증가.",
            "변동성 높으나 상승 추세 유지. 트레일링 스탑 활용 권장.",
        ],
    },
]


def _generate_mock_scores() -> List[dict]:
    """Mock 스코어링 결과 생성"""
    results = []
    now = datetime.now().isoformat()

    for coin in _COIN_POOL:
        lo, hi = coin["score_range"]
        scores = {
            "technical": _rand(lo, hi),
            "momentum": _rand(lo, hi),
            "volatility": _rand(max(25, lo - 10), hi - 5),
            "volume": _rand(lo, hi),
            "sentiment": _rand(max(20, lo - 15), hi - 5),
        }

        total = (
            scores["technical"] * 0.30
            + scores["momentum"] * 0.25
            + scores["volatility"] * 0.15
            + scores["volume"] * 0.15
            + scores["sentiment"] * 0.15
        )

        results.append(
            {
                "symbol": coin["symbol"],
                "name": coin["name"],
                "current_price": coin["base_price"]
                + _rand(-coin["price_range"], coin["price_range"]),
                "price_change_24h": round(random.uniform(-3, 5), 2),
                "technical_score": scores["technical"],
                "momentum_score": scores["momentum"],
                "volatility_score": scores["volatility"],
                "volume_score": scores["volume"],
                "sentiment_score": scores["sentiment"],
                "total_score": round(total, 1),
                "signal": _determine_signal(total),
                "confidence": _rand(45, 95),
                "reasoning": random.choice(coin["reasonings"]),
                "scored_at": now,
            }
        )

    # 점수 내림차순
    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results


def _get_mock_price(symbol: str) -> dict:
    """Mock 현재가"""
    coin = next((c for c in _COIN_POOL if c["symbol"] == symbol.upper()), None)
    if not coin:
        return {}
    return {
        "symbol": coin["symbol"],
        "market": f"KRW-{coin['symbol']}",
        "price": coin["base_price"] + _rand(-coin["price_range"], coin["price_range"]),
        "timestamp": datetime.now().isoformat(),
    }


# ════════════════════════════════════════════════════
# DB 조회 헬퍼
# ════════════════════════════════════════════════════

def _try_db_scores() -> Optional[List[dict]]:
    """
    DB에서 최신 스코어링 결과 조회 시도.
    DB 미연결 시 None 반환 → Mock 폴백.
    """
    try:
        from database.db_manager import DBManager

        db = DBManager()
        query = """
            SELECT DISTINCT ON (symbol)
                symbol,
                technical_score,
                momentum_score,
                volatility_score,
                volume_score,
                sentiment_score,
                total_score,
                signal,
                confidence,
                reasoning,
                scoring_time AS scored_at
            FROM scoring_results
            WHERE scoring_time >= NOW() - INTERVAL '1 hour'
            ORDER BY symbol, scoring_time DESC
        """
        results = db.execute_query(query)
        return results if results else None
    except Exception as e:
        logger.warning("DB 스코어링 조회 실패 → Mock 폴백: %s", e)
        return None


def _try_live_price(symbol: str) -> Optional[dict]:
    """
    업비트 실시간 현재가 조회 시도.
    실패 시 None → Mock 폴백.
    """
    symbol = symbol.upper()
    live_prices = _try_live_prices([symbol])
    if symbol not in live_prices:
        return None

    market = f"KRW-{symbol}"
    price = live_prices[symbol]
    return {
        "symbol": symbol,
        "market": market,
        "price": float(price),
        "timestamp": datetime.now().isoformat(),
    }


def _try_live_prices(symbols: List[str]) -> Dict[str, float]:
    """
    업비트 실시간 현재가를 복수 심볼로 조회.
    실패 시 빈 dict 반환.
    """
    norm_symbols = [s.strip().upper() for s in symbols if s and s.strip()]
    if not norm_symbols:
        return {}

    # 중복 제거 + 순서 유지
    unique_symbols = list(dict.fromkeys(norm_symbols))
    markets = [f"KRW-{s}" for s in unique_symbols]

    try:
        import pyupbit

        logger.info("[Price] Fetching live prices for %s", ",".join(markets))
        result = pyupbit.get_current_price(markets)
        prices: Dict[str, float] = {}

        if isinstance(result, dict):
            for market, price in result.items():
                if price is None:
                    continue
                symbol = market.replace("KRW-", "")
                prices[symbol] = float(price)
            return prices

        if isinstance(result, (int, float)) and len(unique_symbols) == 1:
            prices[unique_symbols[0]] = float(result)
            return prices

        logger.warning("[Price] Unexpected pyupbit response type: %s", type(result))
        return {}
    except Exception as e:
        logger.error("업비트 현재가 일괄 조회 실패 (%s): %s", unique_symbols, e)
        return {}


def _enrich_scores_with_live_prices(scores: List[dict]) -> List[dict]:
    """스코어 결과에 업비트 현재가를 주입."""
    symbols = [str(item.get("symbol", "")).upper() for item in scores if item.get("symbol")]
    live_prices = _try_live_prices(symbols)
    if not live_prices:
        return scores

    for item in scores:
        symbol = str(item.get("symbol", "")).upper()
        if symbol in live_prices:
            item["current_price"] = live_prices[symbol]
    return scores


# ════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════

@router.get(
    "/scores",
    response_model=List[CoinScoreResponse],
    summary="전체 코인 AI 점수",
    description=(
        "멀티팩터 스코어링 엔진의 최신 분석 결과를 반환합니다.\n\n"
        "프론트엔드 `AIRecommendationCards` 컴포넌트가 30초마다 호출합니다.\n"
        "DB 미연결 시 Mock 데이터를 폴백 반환합니다."
    ),
)
async def get_coin_scores():
    """전체 코인 AI 점수 조회"""

    # 1. DB 시도
    db_results = _try_db_scores()
    if db_results:
        logger.info("[스코어] DB에서 %d건 조회", len(db_results))
        return _enrich_scores_with_live_prices(db_results)

    # 2. Mock 폴백
    logger.info("[스코어] Mock 데이터 반환 (DB 미연결)")
    return _enrich_scores_with_live_prices(_generate_mock_scores())


@router.get(
    "/scores/{symbol}",
    response_model=CoinScoreResponse,
    summary="단일 코인 AI 점수",
    description="특정 코인의 상세 스코어링 결과를 반환합니다.",
)
async def get_coin_score(symbol: str):
    """단일 코인 상세 점수"""
    symbol = symbol.upper()

    # DB 시도
    db_results = _try_db_scores()
    if db_results:
        match = next((r for r in db_results if r["symbol"] == symbol), None)
        if match:
            live = _try_live_price(symbol)
            if live:
                match["current_price"] = live["price"]
            return match

    # Mock 폴백
    mock = _generate_mock_scores()
    match = next((r for r in mock if r["symbol"] == symbol), None)
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"코인 '{symbol}'을 찾을 수 없습니다. 지원: BTC, ETH, XRP, SOL",
        )

    live = _try_live_price(symbol)
    if live:
        match["current_price"] = live["price"]
    return match


@router.get(
    "/prices/{symbol}",
    response_model=PriceResponse,
    summary="현재가 조회",
    description="업비트 실시간 현재가를 조회합니다. 업비트 미연결 시 Mock 가격을 반환합니다.",
)
async def get_current_price(symbol: str):
    """현재가 조회"""
    symbol = symbol.upper()

    # 업비트 시도
    live = _try_live_price(symbol)
    if live:
        return live

    # Mock 폴백
    mock = _get_mock_price(symbol)
    if not mock:
        raise HTTPException(
            status_code=404,
            detail=f"코인 '{symbol}' 가격 조회 실패",
        )
    return mock


@router.get(
    "/prices",
    response_model=BatchPriceResponse,
    summary="전체 코인 현재가 일괄 조회",
    description="지원 코인 전체의 현재가를 일괄 조회합니다.",
)
async def get_all_prices(
    symbols: str = Query(
        default="BTC,ETH,XRP,SOL",
        description="조회할 심볼 (콤마 구분)",
        examples=["BTC,ETH,XRP,SOL"],
    ),
):
    """전체 현재가 일괄 조회"""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    live_prices = _try_live_prices(sym_list)
    prices = []

    for sym in sym_list:
        if sym in live_prices:
            prices.append(
                {
                    "symbol": sym,
                    "market": f"KRW-{sym}",
                    "price": live_prices[sym],
                    "timestamp": datetime.now().isoformat(),
                }
            )
            continue

        mock = _get_mock_price(sym)
        if mock:
            prices.append(mock)

    return {"prices": prices, "count": len(prices)}
