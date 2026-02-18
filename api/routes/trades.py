"""
매매 API — /api/trades/*

■ 엔드포인트:
    POST /api/trades/order       → 수동 매수/매도 주문
    GET  /api/trades/history     → 매매 이력 조회
    GET  /api/trades/positions   → 보유 포지션 조회
    GET  /api/trades/balance     → 계좌 잔고
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
import logging
import random
import uuid

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
        default="LIMIT",
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
# Mock 데이터
# ════════════════════════════════════════════════════

# 모의투자 상태 (인메모리)
_paper_balance: float = 1_000_000.0
_paper_trades: List[dict] = []
_paper_positions: List[dict] = []


def _gen_trade_id() -> str:
    return f"T-{uuid.uuid4().hex[:8].upper()}"


def _gen_order_id() -> str:
    return f"ORD-{uuid.uuid4().hex[:10].upper()}"


def _generate_mock_history(limit: int = 10) -> List[dict]:
    """Mock 매매 이력"""
    symbols = ["BTC", "ETH", "SOL", "XRP"]
    sides = ["BUY", "SELL"]
    records = []

    for i in range(min(limit, 20)):
        sym = random.choice(symbols)
        side = random.choice(sides)
        price = {
            "BTC": random.randint(140_000_000, 146_000_000),
            "ETH": random.randint(4_600_000, 5_000_000),
            "SOL": random.randint(270_000, 300_000),
            "XRP": random.randint(3_200, 3_800),
        }[sym]
        amount = random.randint(50_000, 200_000)
        volume = round(amount / price, 8)
        fee = round(amount * 0.0005, 2)

        records.append(
            {
                "trade_id": _gen_trade_id(),
                "symbol": sym,
                "side": side,
                "amount": amount,
                "price": price,
                "volume": volume,
                "fee": fee,
                "pnl_krw": round(random.uniform(-5000, 15000), 2) if side == "SELL" else None,
                "pnl_pct": round(random.uniform(-3, 8), 2) if side == "SELL" else None,
                "trigger_reason": random.choice(["AI_SCORE", "STOP_LOSS", "TAKE_PROFIT", "MANUAL"]),
                "timestamp": datetime.now().isoformat(),
            }
        )

    return records


def _generate_mock_positions() -> List[dict]:
    """Mock 보유 포지션"""
    return [
        {
            "symbol": "BTC",
            "volume": 0.00071,
            "avg_buy_price": 141_500_000,
            "current_price": 143_250_000,
            "current_value": round(0.00071 * 143_250_000, 0),
            "unrealized_pnl": round(0.00071 * (143_250_000 - 141_500_000), 0),
            "unrealized_pnl_pct": round(
                (143_250_000 - 141_500_000) / 141_500_000 * 100, 2
            ),
            "holding_hours": 14.5,
            "bought_at": "2026-02-18T09:00:00",
        },
        {
            "symbol": "SOL",
            "volume": 0.35,
            "avg_buy_price": 280_000,
            "current_price": 285_000,
            "current_value": round(0.35 * 285_000, 0),
            "unrealized_pnl": round(0.35 * (285_000 - 280_000), 0),
            "unrealized_pnl_pct": round(
                (285_000 - 280_000) / 280_000 * 100, 2
            ),
            "holding_hours": 5.2,
            "bought_at": "2026-02-18T18:20:00",
        },
    ]


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
    """수동 주문 생성"""

    # 유효성 검사
    supported = {"BTC", "ETH", "XRP", "SOL"}
    if order.symbol.upper() not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 코인: {order.symbol}. 지원: {', '.join(supported)}",
        )

    if order.amount < 5_000:
        raise HTTPException(
            status_code=400,
            detail="최소 주문 금액은 ₩5,000입니다",
        )

    if order.order_type == "LIMIT" and order.limit_price is None:
        raise HTTPException(
            status_code=400,
            detail="LIMIT 주문에는 limit_price가 필수입니다",
        )

    # TODO: 실제 OrderManager 연동
    # from engine.layer4_execution.order_manager import OrderManager
    # order_mgr = OrderManager(...)
    # result = order_mgr.execute_buy(...) or execute_sell(...)

    order_id = _gen_order_id()
    side_kr = "매수" if order.side == "BUY" else "매도"

    logger.info(
        "[주문] %s %s ₩%s (%s)",
        order.symbol,
        side_kr,
        f"{order.amount:,.0f}",
        order.order_type,
    )

    return OrderResponse(
        success=True,
        order_id=order_id,
        symbol=order.symbol.upper(),
        side=order.side,
        amount=order.amount,
        order_type=order.order_type,
        limit_price=order.limit_price,
        status="SUBMITTED",
        message=f"{order.symbol} {side_kr} 주문이 접수되었습니다 (모의투자 모드)",
        timestamp=datetime.now().isoformat(),
    )


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
    """매매 이력"""

    # TODO: DB 연동
    # db.get_trade_history(limit=limit, symbol=symbol)

    records = _generate_mock_history(limit)

    if symbol:
        records = [r for r in records if r["symbol"] == symbol.upper()]

    return records[:limit]


@router.get(
    "/positions",
    response_model=List[Position],
    summary="보유 포지션 조회",
    description="현재 보유 중인 코인 포지션 목록을 반환합니다.",
)
async def get_positions():
    """보유 포지션"""

    # TODO: DB 연동
    # positions = db.get_open_positions()

    return _generate_mock_positions()


@router.get(
    "/balance",
    response_model=BalanceResponse,
    summary="계좌 잔고 조회",
    description="원화 잔고 + 포지션 평가금을 포함한 총 자산을 반환합니다.",
)
async def get_balance():
    """계좌 잔고"""

    # TODO: 실제 OrderManager.get_balance() 연동

    positions = _generate_mock_positions()
    positions_value = sum(p["current_value"] for p in positions)
    available_krw = 900_000.0

    return BalanceResponse(
        total_krw=available_krw,
        available_krw=available_krw,
        positions_value=positions_value,
        total_value=available_krw + positions_value,
    )
