"""
매매 API — /api/trades/*

■ 엔드포인트:
    POST /api/trades/order         → 수동 매수/매도 주문
    POST /api/trades/manual-order  → 레거시 별칭 (order와 동일)
    GET  /api/trades/history       → 매매 이력 조회
    GET  /api/trades/positions     → 보유 포지션 조회
    GET  /api/trades/balance       → 계좌 잔고

모드:
    - paper: 인메모리 모의투자
    - live : 업비트 실계좌 연동
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal, Any
from datetime import datetime
import logging
import os
import uuid
import hashlib
from urllib.parse import urlencode
from threading import Lock

import httpx
import jwt

logger = logging.getLogger("cryptoai.api.trades")

router = APIRouter()


# ════════════════════════════════════════════════════
# Pydantic 스키마
# ════════════════════════════════════════════════════

class OrderRequest(BaseModel):
    """주문 요청 스키마"""

    symbol: str = Field(
        ...,
        description="코인 심볼 (BTC, ETH 등)",
        examples=["BTC"],
    )
    side: Literal["BUY", "SELL"] = Field(
        ...,
        description="매수/매도 구분",
        examples=["BUY"],
    )
    amount: float = Field(
        ...,
        gt=0,
        description="주문 금액 (KRW)",
        examples=[100000],
    )
    order_type: Literal["MARKET", "LIMIT"] = Field(
        default="MARKET",
        description="주문 유형 (시장가/지정가)",
    )
    limit_price: Optional[float] = Field(
        None,
        description="지정가 (LIMIT 주문 시 필수)",
    )


class OrderResponse(BaseModel):
    """주문 응답 스키마"""

    success: bool
    order_id: str = Field(..., description="주문 고유 ID")
    symbol: str
    side: str
    amount: float
    order_type: str
    limit_price: Optional[float] = None
    status: str = Field(..., description="SUBMITTED | FILLED | REJECTED")
    message: str
    timestamp: str


class TradeRecord(BaseModel):
    """매매 기록 스키마"""

    trade_id: str
    symbol: str
    side: str
    amount: float = Field(..., description="주문 금액 (KRW)")
    price: float = Field(..., description="체결 가격")
    volume: float = Field(..., description="체결 수량")
    fee: float = Field(..., description="수수료")
    pnl_krw: Optional[float] = Field(None, description="실현 손익 (KRW)")
    pnl_pct: Optional[float] = Field(None, description="실현 손익 (%)")
    trigger_reason: Optional[str] = Field(None, description="트리거 사유 (AI/STOP_LOSS 등)")
    timestamp: str


class Position(BaseModel):
    """보유 포지션 스키마"""

    symbol: str
    volume: float = Field(..., description="보유 수량")
    avg_buy_price: float = Field(..., description="평균 매수가")
    current_price: float = Field(..., description="현재가")
    current_value: float = Field(..., description="평가 금액 (KRW)")
    unrealized_pnl: float = Field(..., description="미실현 손익 (KRW)")
    unrealized_pnl_pct: float = Field(..., description="미실현 손익 (%)")
    holding_hours: float = Field(..., description="보유 시간 (h)")
    bought_at: str


class BalanceResponse(BaseModel):
    """잔고 응답 스키마"""

    total_krw: float = Field(..., description="총 원화 잔고")
    available_krw: float = Field(..., description="주문 가능 원화")
    positions_value: float = Field(..., description="포지션 평가 금액")
    total_value: float = Field(..., description="총 자산 (원화 + 포지션)")


# ════════════════════════════════════════════════════
# 공통 상수/유틸
# ════════════════════════════════════════════════════

FEE_RATE = 0.0005
SUPPORTED_SYMBOLS = {"BTC", "ETH", "XRP", "SOL"}


def _gen_trade_id() -> str:
    return f"T-{uuid.uuid4().hex[:8].upper()}"


def _gen_order_id() -> str:
    return f"ORD-{uuid.uuid4().hex[:10].upper()}"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_live_mode() -> bool:
    return os.environ.get("TRADING_MODE", "paper").strip().lower() == "live"


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _extract_upbit_error(resp: Any) -> Optional[str]:
    if isinstance(resp, dict):
        err = resp.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("name") or "업비트 API 오류")
    return None


def _get_upbit_keys() -> tuple[str, str]:
    access_key = os.environ.get("UPBIT_API_KEY", "").strip()
    secret_key = os.environ.get("UPBIT_SECRET_KEY", "").strip()

    if not access_key or not secret_key or "your_upbit" in access_key.lower() or "your_upbit" in secret_key.lower():
        raise HTTPException(
            status_code=503,
            detail="실거래 모드이지만 업비트 API 키가 설정되지 않았습니다",
        )
    return access_key, secret_key


def _make_upbit_jwt(secret_key: str, access_key: str, params: Optional[Dict[str, Any]] = None) -> str:
    payload: Dict[str, Any] = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
    }
    if params:
        query_string = urlencode(params, doseq=True)
        payload["query_hash"] = hashlib.sha512(query_string.encode()).hexdigest()
        payload["query_hash_alg"] = "SHA512"

    token = jwt.encode(payload, secret_key, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode()
    return token


def _upbit_private_request(method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """
    업비트 Private API 요청 (pyupbit private 파서 우회).
    """
    access_key, secret_key = _get_upbit_keys()
    token = _make_upbit_jwt(secret_key=secret_key, access_key=access_key, params=params)
    headers = {"Authorization": f"Bearer {token}"}

    url = f"https://api.upbit.com{path}"
    try:
        response = httpx.request(
            method=method.upper(),
            url=url,
            params=params if params else None,
            headers=headers,
            timeout=10.0,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"업비트 연결 실패: {e}")

    body: Any
    try:
        body = response.json()
    except Exception:
        body = {"error": {"message": response.text or "응답 파싱 실패"}}

    if response.status_code >= 400:
        err_msg = _extract_upbit_error(body) or f"HTTP {response.status_code}"
        if response.status_code in (401, 403):
            err_msg = f"{err_msg} (허용 IP/권한/API 키 상태 확인)"
        raise HTTPException(status_code=503, detail=f"업비트 인증/요청 실패: {err_msg}")

    return body


def _get_live_balances_rows() -> List[dict]:
    rows = _upbit_private_request("GET", "/v1/accounts")
    if not isinstance(rows, list):
        raise HTTPException(status_code=503, detail="업비트 잔고 응답 형식 오류")
    return [row for row in rows if isinstance(row, dict)]


def _get_live_price(symbol: str) -> Optional[float]:
    """업비트 현재가 조회. 실패 시 None."""
    try:
        import pyupbit

        price = pyupbit.get_current_price(f"KRW-{symbol}")
        if not price:
            return None
        return float(price)
    except Exception:
        return None


def _get_live_prices(symbols: List[str]) -> Dict[str, float]:
    try:
        import pyupbit

        markets = [f"KRW-{s}" for s in symbols]
        result = pyupbit.get_current_price(markets)
        prices: Dict[str, float] = {}

        if isinstance(result, dict):
            for market, price in result.items():
                sym = market.replace("KRW-", "")
                if price is not None:
                    prices[sym] = float(price)
        elif isinstance(result, (int, float)) and len(symbols) == 1:
            prices[symbols[0]] = float(result)

        return prices
    except Exception:
        return {}


# ════════════════════════════════════════════════════
# paper 모드 상태 (인메모리)
# ════════════════════════════════════════════════════

_state_lock = Lock()
_paper_balance: float = 1_000_000.0
_paper_trades: List[dict] = []
# symbol -> {symbol, volume, avg_buy_price, bought_at}
_paper_positions: Dict[str, dict] = {}


def _paper_get_price(symbol: str, order_type: str, limit_price: Optional[float]) -> float:
    if order_type == "LIMIT":
        if limit_price is None:
            raise HTTPException(status_code=400, detail="LIMIT 주문에는 limit_price가 필수입니다")
        if limit_price <= 0:
            raise HTTPException(status_code=400, detail="limit_price는 0보다 커야 합니다")
        return float(limit_price)

    live = _get_live_price(symbol)
    if live is None:
        raise HTTPException(status_code=503, detail=f"{symbol} 현재가 조회 실패")
    return live


def _paper_positions_list() -> List[dict]:
    now = datetime.now()
    rows: List[dict] = []

    for symbol, pos in _paper_positions.items():
        current_price = _get_live_price(symbol) or pos["avg_buy_price"]
        current_value = pos["volume"] * current_price
        unrealized_pnl = (current_price - pos["avg_buy_price"]) * pos["volume"]
        unrealized_pnl_pct = 0.0
        if pos["avg_buy_price"] > 0:
            unrealized_pnl_pct = ((current_price - pos["avg_buy_price"]) / pos["avg_buy_price"]) * 100

        bought_at = datetime.fromisoformat(pos["bought_at"])
        holding_hours = (now - bought_at).total_seconds() / 3600

        rows.append(
            {
                "symbol": symbol,
                "volume": round(pos["volume"], 8),
                "avg_buy_price": round(pos["avg_buy_price"], 2),
                "current_price": round(current_price, 2),
                "current_value": round(current_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "holding_hours": round(holding_hours, 2),
                "bought_at": pos["bought_at"],
            }
        )

    return sorted(rows, key=lambda x: x["symbol"])


def _create_paper_order(order: OrderRequest) -> OrderResponse:
    symbol = _normalize_symbol(order.symbol)
    exec_price = _paper_get_price(symbol, order.order_type, order.limit_price)
    if exec_price <= 0:
        raise HTTPException(status_code=400, detail="체결 가격 계산 실패")

    order_id = _gen_order_id()
    now_iso = datetime.now().isoformat()
    fee = round(order.amount * FEE_RATE, 2)

    with _state_lock:
        global _paper_balance

        if order.side == "BUY":
            required = order.amount + fee
            if _paper_balance < required:
                raise HTTPException(
                    status_code=400,
                    detail=f"잔고 부족: 필요 ₩{required:,.0f}, 가용 ₩{_paper_balance:,.0f}",
                )

            volume = order.amount / exec_price
            _paper_balance -= required

            existing = _paper_positions.get(symbol)
            if existing:
                new_volume = existing["volume"] + volume
                existing_total_cost = existing["avg_buy_price"] * existing["volume"]
                new_total_cost = existing_total_cost + order.amount
                existing["volume"] = new_volume
                existing["avg_buy_price"] = new_total_cost / new_volume
            else:
                _paper_positions[symbol] = {
                    "symbol": symbol,
                    "volume": volume,
                    "avg_buy_price": exec_price,
                    "bought_at": now_iso,
                }

            _paper_trades.append(
                {
                    "trade_id": _gen_trade_id(),
                    "symbol": symbol,
                    "side": "BUY",
                    "amount": round(order.amount, 2),
                    "price": round(exec_price, 2),
                    "volume": round(volume, 8),
                    "fee": fee,
                    "pnl_krw": None,
                    "pnl_pct": None,
                    "trigger_reason": "MANUAL",
                    "timestamp": now_iso,
                }
            )

            message = f"{symbol} 매수 주문 체결 (모의투자)"

        else:
            pos = _paper_positions.get(symbol)
            if not pos or pos["volume"] <= 0:
                raise HTTPException(status_code=400, detail=f"{symbol} 보유 수량이 없습니다")

            sell_volume = order.amount / exec_price
            sell_volume = min(sell_volume, pos["volume"])
            sell_amount = sell_volume * exec_price
            fee = round(sell_amount * FEE_RATE, 2)

            if sell_amount < 5_000:
                raise HTTPException(status_code=400, detail="최소 주문 금액은 ₩5,000입니다")

            realized_pnl = (exec_price - pos["avg_buy_price"]) * sell_volume
            realized_pnl_pct = 0.0
            if pos["avg_buy_price"] > 0:
                realized_pnl_pct = ((exec_price - pos["avg_buy_price"]) / pos["avg_buy_price"]) * 100

            _paper_balance += max(0.0, sell_amount - fee)
            pos["volume"] -= sell_volume
            if pos["volume"] <= 1e-12:
                _paper_positions.pop(symbol, None)

            _paper_trades.append(
                {
                    "trade_id": _gen_trade_id(),
                    "symbol": symbol,
                    "side": "SELL",
                    "amount": round(sell_amount, 2),
                    "price": round(exec_price, 2),
                    "volume": round(sell_volume, 8),
                    "fee": fee,
                    "pnl_krw": round(realized_pnl, 2),
                    "pnl_pct": round(realized_pnl_pct, 2),
                    "trigger_reason": "MANUAL",
                    "timestamp": now_iso,
                }
            )

            message = f"{symbol} 매도 주문 체결 (모의투자)"

    return OrderResponse(
        success=True,
        order_id=order_id,
        symbol=symbol,
        side=order.side,
        amount=order.amount,
        order_type=order.order_type,
        limit_price=order.limit_price,
        status="FILLED",
        message=message,
        timestamp=now_iso,
    )


# ════════════════════════════════════════════════════
# live 모드 헬퍼
# ════════════════════════════════════════════════════


def _create_live_order(order: OrderRequest) -> OrderResponse:
    symbol = _normalize_symbol(order.symbol)
    market = f"KRW-{symbol}"

    if order.side == "BUY" and order.amount < 5_000:
        raise HTTPException(status_code=400, detail="최소 주문 금액은 ₩5,000입니다")

    try:
        params: Dict[str, Any]
        executed_amount = float(order.amount)

        if order.side == "BUY":
            if order.order_type == "MARKET":
                params = {
                    "market": market,
                    "side": "bid",
                    "ord_type": "price",
                    "price": str(int(order.amount)),
                }
            else:
                if order.limit_price is None or order.limit_price <= 0:
                    raise HTTPException(status_code=400, detail="LIMIT 주문에는 유효한 limit_price가 필요합니다")
                volume = float(order.amount) / float(order.limit_price)
                params = {
                    "market": market,
                    "side": "bid",
                    "ord_type": "limit",
                    "price": str(order.limit_price),
                    "volume": str(volume),
                }

        else:
            balances = _get_live_balances_rows()
            owned = next(
                (row for row in balances if str(row.get("currency", "")).upper() == symbol),
                None,
            )
            available_volume = _as_float(owned.get("balance")) if owned else 0.0
            if available_volume <= 0:
                raise HTTPException(status_code=400, detail=f"{symbol} 보유 수량이 없습니다")

            ref_price = order.limit_price if order.order_type == "LIMIT" else _get_live_price(symbol)
            if ref_price is None or ref_price <= 0:
                raise HTTPException(status_code=400, detail=f"{symbol} 현재가 조회 실패")

            target_volume = float(order.amount) / float(ref_price)
            sell_volume = min(target_volume, available_volume)
            executed_amount = sell_volume * float(ref_price)

            if sell_volume <= 0:
                raise HTTPException(status_code=400, detail=f"{symbol} 보유 수량이 없습니다")
            if executed_amount < 5_000:
                raise HTTPException(status_code=400, detail="최소 주문 금액은 ₩5,000입니다")

            if order.order_type == "MARKET":
                params = {
                    "market": market,
                    "side": "ask",
                    "ord_type": "market",
                    "volume": str(sell_volume),
                }
            else:
                if order.limit_price is None or order.limit_price <= 0:
                    raise HTTPException(status_code=400, detail="LIMIT 주문에는 유효한 limit_price가 필요합니다")
                params = {
                    "market": market,
                    "side": "ask",
                    "ord_type": "limit",
                    "price": str(order.limit_price),
                    "volume": str(sell_volume),
                }

        response = _upbit_private_request("POST", "/v1/orders", params=params)
        err = _extract_upbit_error(response)
        if err:
            raise HTTPException(status_code=400, detail=f"업비트 주문 실패: {err}")

        order_uuid = ""
        if isinstance(response, dict):
            order_uuid = str(response.get("uuid", ""))

        return OrderResponse(
            success=True,
            order_id=order_uuid or _gen_order_id(),
            symbol=symbol,
            side=order.side,
            amount=executed_amount,
            order_type=order.order_type,
            limit_price=order.limit_price,
            status="SUBMITTED",
            message=f"{symbol} {order.side} 주문이 업비트로 전송되었습니다",
            timestamp=datetime.now().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"업비트 주문 처리 중 오류: {e}")


def _get_live_positions() -> List[dict]:
    balances = _get_live_balances_rows()

    owned_symbols: List[str] = []
    raw_rows: Dict[str, dict] = {}

    for row in balances:
        if not isinstance(row, dict):
            continue
        currency = str(row.get("currency", "")).upper()
        if currency not in SUPPORTED_SYMBOLS:
            continue

        balance = _as_float(row.get("balance"))
        locked = _as_float(row.get("locked"))
        volume = balance + locked
        if volume <= 0:
            continue

        owned_symbols.append(currency)
        raw_rows[currency] = row

    price_map = _get_live_prices(owned_symbols)
    now_iso = datetime.now().isoformat()

    result: List[dict] = []
    for symbol in owned_symbols:
        row = raw_rows[symbol]
        volume = _as_float(row.get("balance")) + _as_float(row.get("locked"))
        avg_buy_price = _as_float(row.get("avg_buy_price"))
        current_price = price_map.get(symbol, avg_buy_price if avg_buy_price > 0 else 0.0)

        current_value = volume * current_price
        unrealized_pnl = (current_price - avg_buy_price) * volume
        unrealized_pnl_pct = 0.0
        if avg_buy_price > 0:
            unrealized_pnl_pct = ((current_price - avg_buy_price) / avg_buy_price) * 100

        result.append(
            {
                "symbol": symbol,
                "volume": round(volume, 8),
                "avg_buy_price": round(avg_buy_price, 2),
                "current_price": round(current_price, 2),
                "current_value": round(current_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "holding_hours": 0.0,
                "bought_at": now_iso,
            }
        )

    return sorted(result, key=lambda x: x["symbol"])


def _get_live_trade_history(limit: int, symbol_filter: Optional[str]) -> List[dict]:
    symbols = [symbol_filter] if symbol_filter else sorted(SUPPORTED_SYMBOLS)

    records: List[dict] = []
    failed_count = 0
    first_error_detail: Optional[str] = None
    for symbol in symbols:
        market = f"KRW-{symbol}"
        try:
            rows = _upbit_private_request(
                "GET",
                "/v1/orders",
                params={"market": market, "state": "done", "page": 1, "limit": limit},
            )
        except HTTPException as e:
            failed_count += 1
            first_error_detail = first_error_detail or str(e.detail)
            logger.warning("[이력] %s 조회 실패: %s", market, e.detail)
            if symbol_filter:
                raise
            continue

        err = _extract_upbit_error(rows)
        if err:
            logger.warning("[이력] %s 응답 오류: %s", market, err)
            continue

        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            side_raw = str(row.get("side", "")).lower()
            side = "BUY" if side_raw == "bid" else "SELL"

            volume = _as_float(row.get("executed_volume"))
            if volume <= 0:
                volume = _as_float(row.get("volume"))

            price = _as_float(row.get("price"))
            if price <= 0:
                price = _get_live_price(symbol) or 0.0

            amount = _as_float(row.get("locked"))
            if amount <= 0 and volume > 0 and price > 0:
                amount = volume * price

            fee = _as_float(row.get("paid_fee"))
            created_at = str(row.get("created_at") or datetime.now().isoformat())

            records.append(
                {
                    "trade_id": str(row.get("uuid") or _gen_trade_id()),
                    "symbol": symbol,
                    "side": side,
                    "amount": round(amount, 2),
                    "price": round(price, 2),
                    "volume": round(volume, 8),
                    "fee": round(fee, 2),
                    "pnl_krw": None,
                    "pnl_pct": None,
                    "trigger_reason": "MANUAL",
                    "timestamp": created_at,
                }
            )

    # created_at ISO 문자열 기준 내림차순
    if not records and failed_count == len(symbols) and first_error_detail:
        raise HTTPException(status_code=503, detail=first_error_detail)

    records.sort(key=lambda x: x["timestamp"], reverse=True)
    return records[:limit]


# ════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════

@router.post(
    "/order",
    response_model=OrderResponse,
    summary="수동 매수/매도 주문",
    description=(
        "프론트엔드의 '💰 지금 매수' 버튼으로 호출됩니다.\n\n"
        "- **최소 주문 금액**: ₩5,000\n"
        "- **지원 코인**: BTC, ETH, XRP, SOL\n"
        "- **주문 유형**: MARKET (시장가), LIMIT (지정가)"
    ),
)
async def create_order(order: OrderRequest):
    """수동 주문 생성.

    live 모드에서는 업비트 실거래 주문을 전송합니다.
    """
    symbol = _normalize_symbol(order.symbol)
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 코인: {order.symbol}. 지원: {', '.join(sorted(SUPPORTED_SYMBOLS))}",
        )

    if _is_live_mode():
        result = _create_live_order(order)
        logger.warning("[실거래 주문] %s %s ₩%s (%s)", symbol, order.side, f"{order.amount:,.0f}", order.order_type)
        return result

    result = _create_paper_order(order)
    logger.info("[모의주문] %s %s ₩%s (%s)", symbol, order.side, f"{order.amount:,.0f}", order.order_type)
    return result


@router.post(
    "/manual-order",
    response_model=OrderResponse,
    include_in_schema=False,
)
async def create_manual_order_alias(order: OrderRequest):
    """레거시 호환: /manual-order -> /order."""
    return await create_order(order)


@router.get(
    "/history",
    response_model=List[TradeRecord],
    summary="매매 이력 조회",
    description="최근 매매 기록을 시간 역순으로 반환합니다.",
)
async def get_trade_history(
    limit: int = Query(default=20, ge=1, le=100, description="조회 건수"),
    symbol: Optional[str] = Query(default=None, description="코인 필터"),
):
    """매매 이력."""
    symbol_filter = _normalize_symbol(symbol) if symbol else None

    if symbol_filter and symbol_filter not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 코인: {symbol_filter}")

    if _is_live_mode():
        return _get_live_trade_history(limit=limit, symbol_filter=symbol_filter)

    with _state_lock:
        records = list(reversed(_paper_trades))

    if symbol_filter:
        records = [r for r in records if r["symbol"] == symbol_filter]

    return records[:limit]


@router.get(
    "/positions",
    response_model=List[Position],
    summary="보유 포지션 조회",
    description="현재 보유 중인 코인 포지션 목록을 반환합니다.",
)
async def get_positions():
    """보유 포지션."""
    if _is_live_mode():
        return _get_live_positions()

    with _state_lock:
        return _paper_positions_list()


@router.get(
    "/balance",
    response_model=BalanceResponse,
    summary="계좌 잔고 조회",
    description="원화 잔고 + 포지션 평가금을 포함한 총 자산을 반환합니다.",
)
async def get_balance():
    """계좌 잔고."""

    if _is_live_mode():
        balances = _get_live_balances_rows()

        available_krw = 0.0
        locked_krw = 0.0
        if isinstance(balances, list):
            for row in balances:
                if isinstance(row, dict) and str(row.get("currency", "")).upper() == "KRW":
                    available_krw = _as_float(row.get("balance"))
                    locked_krw = _as_float(row.get("locked"))
                    break

        positions = _get_live_positions()
        positions_value = sum(p["current_value"] for p in positions)
        total_krw = round(available_krw + locked_krw, 2)

        return BalanceResponse(
            total_krw=total_krw,
            available_krw=round(available_krw, 2),
            positions_value=round(positions_value, 2),
            total_value=round(total_krw + positions_value, 2),
        )

    with _state_lock:
        positions = _paper_positions_list()
        positions_value = sum(p["current_value"] for p in positions)
        available_krw = round(_paper_balance, 2)

    return BalanceResponse(
        total_krw=available_krw,
        available_krw=available_krw,
        positions_value=round(positions_value, 2),
        total_value=round(available_krw + positions_value, 2),
    )
