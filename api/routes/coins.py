"""코인 스코어/시세 API."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import logging
import time
from threading import Lock

router = APIRouter()
logger = logging.getLogger("cryptoai.api.coins")

SUPPORTED_SYMBOLS = ("BTC", "ETH", "XRP", "SOL")
COIN_NAMES = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "XRP": "Ripple",
    "SOL": "Solana",
}
SCORING_WEIGHTS = {
    "technical": 0.30,
    "momentum": 0.25,
    "volatility": 0.15,
    "volume": 0.15,
    "sentiment": 0.15,
}
TICKER_CACHE_TTL_SECONDS = 5.0
_ticker_cache_lock = Lock()
_ticker_cache_ts = 0.0
_ticker_cache_data: Dict[str, Dict[str, float]] = {}


class CoinScoreResponse(BaseModel):
    symbol: str = Field(..., description="코인 심볼")
    name: str = Field("", description="코인명")
    current_price: Optional[float] = Field(None, description="현재가 (KRW)")
    price_change_24h: Optional[float] = Field(None, description="24시간 변동률 (%)")
    technical_score: float = Field(..., ge=0, le=100)
    momentum_score: float = Field(..., ge=0, le=100)
    volatility_score: float = Field(..., ge=0, le=100)
    volume_score: float = Field(..., ge=0, le=100)
    sentiment_score: float = Field(..., ge=0, le=100)
    total_score: float = Field(..., ge=0, le=100)
    signal: str = Field(..., pattern="^(STRONG_BUY|BUY|HOLD|SELL)$")
    confidence: float = Field(..., ge=0, le=100)
    reasoning: str
    scored_at: Optional[str] = Field(None, description="스코어링 시각 (ISO)")


class PriceResponse(BaseModel):
    symbol: str
    market: str
    price: float
    timestamp: str


class BatchPriceResponse(BaseModel):
    prices: List[PriceResponse]
    count: int


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_symbols(symbols: List[str]) -> List[str]:
    unique: List[str] = []
    for symbol in symbols:
        norm = _normalize_symbol(symbol)
        if norm in SUPPORTED_SYMBOLS and norm not in unique:
            unique.append(norm)
    return unique


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _determine_signal(total_score: float) -> str:
    if total_score >= 80:
        return "STRONG_BUY"
    if total_score >= 70:
        return "BUY"
    if total_score <= 30:
        return "SELL"
    return "HOLD"


def _get_cached_ticker_rows(symbols: List[str], allow_stale: bool = False) -> Dict[str, Dict[str, float]]:
    now = time.time()
    with _ticker_cache_lock:
        if not _ticker_cache_data:
            return {}
        age = now - _ticker_cache_ts
        if not allow_stale and age > TICKER_CACHE_TTL_SECONDS:
            return {}
        if any(symbol not in _ticker_cache_data for symbol in symbols):
            return {}
        return {symbol: dict(_ticker_cache_data[symbol]) for symbol in symbols}


def _set_cached_ticker_rows(rows: Dict[str, Dict[str, float]]) -> None:
    global _ticker_cache_ts
    if not rows:
        return
    with _ticker_cache_lock:
        _ticker_cache_data.update(rows)
        _ticker_cache_ts = time.time()


def _fetch_ticker_rows(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    norm_symbols = _normalize_symbols(symbols)
    if not norm_symbols:
        return {}

    cached = _get_cached_ticker_rows(norm_symbols, allow_stale=False)
    if cached:
        return cached

    markets = [f"KRW-{symbol}" for symbol in norm_symbols]
    try:
        response = httpx.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(markets)},
            timeout=5.0,
        )
        response.raise_for_status()
        rows = response.json()
    except Exception as exc:
        stale = _get_cached_ticker_rows(norm_symbols, allow_stale=True)
        if stale:
            logger.warning("업비트 시세 조회 실패, stale 캐시 사용: %s", exc)
            return stale
        raise HTTPException(status_code=502, detail=f"업비트 시세 조회 실패: {exc}")

    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="업비트 시세 응답 형식 오류")

    result: Dict[str, Dict[str, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market", ""))
        symbol = market.replace("KRW-", "")
        if symbol not in norm_symbols:
            continue

        trade_price = row.get("trade_price")
        signed_change_rate = row.get("signed_change_rate")
        if trade_price is None:
            continue

        item: Dict[str, float] = {
            "price": _to_float(trade_price),
            "signed_change_rate": _to_float(signed_change_rate),
            "opening_price": _to_float(row.get("opening_price")),
            "high_price": _to_float(row.get("high_price")),
            "low_price": _to_float(row.get("low_price")),
            "acc_trade_price_24h": _to_float(row.get("acc_trade_price_24h")),
        }
        if signed_change_rate is not None:
            item["price_change_24h"] = round(float(signed_change_rate) * 100, 2)
        result[symbol] = item

    _set_cached_ticker_rows(result)
    return result


def _fetch_live_ticker_stats(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    rows = _fetch_ticker_rows(symbols)
    result: Dict[str, Dict[str, float]] = {}
    for symbol, row in rows.items():
        result[symbol] = {
            "price": row.get("price", 0.0),
            "price_change_24h": row.get("price_change_24h", 0.0),
        }
    return result


def _build_live_scores(symbols: List[str]) -> List[dict]:
    """DB 미구성 시 업비트 실시간 데이터로 즉시 점수를 계산합니다."""
    target_symbols = _normalize_symbols(symbols)
    rows = _fetch_ticker_rows(target_symbols)
    if not rows:
        raise HTTPException(status_code=502, detail="업비트 실시간 스코어 데이터 생성 실패")

    volumes = {
        symbol: rows[symbol].get("acc_trade_price_24h", 0.0)
        for symbol in target_symbols
        if symbol in rows
    }
    sorted_symbols = sorted(volumes, key=lambda s: volumes[s], reverse=True)
    volume_rank: Dict[str, float] = {}
    if sorted_symbols:
        denom = max(1, len(sorted_symbols) - 1)
        for rank, symbol in enumerate(sorted_symbols):
            volume_rank[symbol] = 1.0 - (rank / denom)

    now = datetime.now().isoformat()
    output: List[dict] = []
    for symbol in target_symbols:
        row = rows.get(symbol)
        if not row:
            continue

        current = _to_float(row.get("price"))
        opening = _to_float(row.get("opening_price"), current)
        high = _to_float(row.get("high_price"), current)
        low = _to_float(row.get("low_price"), current)
        change_pct = _to_float(row.get("signed_change_rate")) * 100.0

        if high < low:
            high, low = low, high
        day_range = max(0.0, high - low)
        range_pos = 0.5 if day_range == 0 else (current - low) / day_range
        range_pos = _clamp(range_pos, 0.0, 1.0)
        range_pct = 0.0 if opening <= 0 else ((high - low) / opening) * 100.0

        technical = _clamp(55.0 + (0.5 - range_pos) * 42.0)
        momentum = _clamp(50.0 + change_pct * 8.0)
        volatility = _clamp(75.0 - abs(range_pct - 4.0) * 9.0)
        volume = _clamp(30.0 + volume_rank.get(symbol, 0.5) * 70.0)
        sentiment = _clamp(50.0 + (-change_pct) * 6.0)

        total = _clamp(
            SCORING_WEIGHTS["technical"] * technical
            + SCORING_WEIGHTS["momentum"] * momentum
            + SCORING_WEIGHTS["volatility"] * volatility
            + SCORING_WEIGHTS["volume"] * volume
            + SCORING_WEIGHTS["sentiment"] * sentiment
        )
        signal = _determine_signal(total)

        consistency = 100.0 - (max(technical, momentum, volatility, volume, sentiment) - min(technical, momentum, volatility, volume, sentiment))
        confidence = _clamp((consistency * 0.6) + (abs(change_pct) * 3.0))

        reasons: List[str] = []
        if technical >= 65:
            reasons.append("당일 저점권 접근")
        if momentum >= 65:
            reasons.append("단기 상승 모멘텀")
        if volume >= 70:
            reasons.append("거래대금 상위")
        if sentiment >= 65:
            reasons.append("공포 구간 역발상")
        if not reasons:
            reasons.append("실시간 흐름 관망")

        output.append(
            {
                "symbol": symbol,
                "name": COIN_NAMES.get(symbol, symbol),
                "current_price": current,
                "price_change_24h": round(change_pct, 2),
                "technical_score": round(technical, 2),
                "momentum_score": round(momentum, 2),
                "volatility_score": round(volatility, 2),
                "volume_score": round(volume, 2),
                "sentiment_score": round(sentiment, 2),
                "total_score": round(total, 2),
                "signal": signal,
                "confidence": round(confidence, 2),
                "reasoning": f"{symbol}: " + ", ".join(reasons),
                "scored_at": now,
            }
        )

    output.sort(key=lambda row: row.get("total_score", 0), reverse=True)
    return output


def _load_latest_scores_from_db() -> List[dict]:
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
        rows = db.execute_query(query)
        return rows
    except Exception as exc:
        logger.warning("스코어 DB 조회 실패, 실시간 fallback 사용: %s", exc)
        return []


def _enrich_scores_with_ticker(scores: List[dict]) -> List[dict]:
    symbols = [str(item.get("symbol", "")).upper() for item in scores if item.get("symbol")]
    stats = _fetch_live_ticker_stats(symbols)

    enriched: List[dict] = []
    for item in scores:
        symbol = str(item.get("symbol", "")).upper()
        row = dict(item)
        row["symbol"] = symbol
        row["name"] = COIN_NAMES.get(symbol, symbol)
        if symbol in stats:
            row["current_price"] = stats[symbol].get("price")
            row["price_change_24h"] = stats[symbol].get("price_change_24h")
        enriched.append(row)
    return enriched


@router.get(
    "/scores",
    response_model=List[CoinScoreResponse],
    summary="전체 코인 AI 점수",
)
async def get_coin_scores():
    scores = _load_latest_scores_from_db()
    if scores:
        return _enrich_scores_with_ticker(scores)
    return _build_live_scores(list(SUPPORTED_SYMBOLS))


@router.get(
    "/scores/{symbol}",
    response_model=CoinScoreResponse,
    summary="단일 코인 AI 점수",
)
async def get_coin_score(symbol: str):
    symbol = _normalize_symbol(symbol)
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 코인: {symbol}")

    scores = _load_latest_scores_from_db()
    if scores:
        enriched = _enrich_scores_with_ticker(scores)
    else:
        enriched = _build_live_scores([symbol])

    match = next((row for row in enriched if row.get("symbol") == symbol), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"{symbol} 스코어링 데이터가 없습니다")
    return match


@router.get(
    "/prices/{symbol}",
    response_model=PriceResponse,
    summary="단일 코인 현재가",
)
async def get_current_price(symbol: str):
    symbol = _normalize_symbol(symbol)
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 코인: {symbol}")

    stats = _fetch_live_ticker_stats([symbol])
    if symbol not in stats:
        raise HTTPException(status_code=502, detail=f"{symbol} 현재가 조회 실패")

    return {
        "symbol": symbol,
        "market": f"KRW-{symbol}",
        "price": float(stats[symbol]["price"]),
        "timestamp": datetime.now().isoformat(),
    }


@router.get(
    "/prices",
    response_model=BatchPriceResponse,
    summary="복수 코인 현재가",
)
async def get_all_prices(
    symbols: str = Query(default="BTC,ETH,XRP,SOL", description="조회할 심볼(콤마 구분)"),
):
    raw_symbols = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
    target_symbols = _normalize_symbols(raw_symbols)
    if not target_symbols:
        raise HTTPException(status_code=400, detail="유효한 심볼이 없습니다")

    stats = _fetch_live_ticker_stats(target_symbols)
    prices: List[dict] = []
    for symbol in target_symbols:
        if symbol not in stats:
            continue
        prices.append(
            {
                "symbol": symbol,
                "market": f"KRW-{symbol}",
                "price": float(stats[symbol]["price"]),
                "timestamp": datetime.now().isoformat(),
            }
        )

    if not prices:
        raise HTTPException(status_code=502, detail="업비트 가격 데이터가 없습니다")

    return {"prices": prices, "count": len(prices)}
