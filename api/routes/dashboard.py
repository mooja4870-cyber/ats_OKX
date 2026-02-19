"""대시보드 API — /api/dashboard/*"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

try:
    from api.routes import coins, trades
except ImportError:
    from routes import coins, trades

router = APIRouter()
KST = ZoneInfo("Asia/Seoul")


class DashboardOverviewResponse(BaseModel):
    """대시보드 요약 응답."""

    total_value: float = Field(..., description="총 자산")
    available_krw: float = Field(..., description="주문 가능 원화")
    positions_count: int = Field(..., description="보유 포지션 수")
    ai_accuracy: float = Field(..., description="AI 정확도(승률, %)")
    ai_wins: int = Field(..., description="수익 거래 수")
    ai_closed_trades: int = Field(..., description="종료 거래 수")
    top_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    updated_at: str = Field(..., description="업데이트 시각")


class AIAccuracyResponse(BaseModel):
    """AI 정확도 응답."""

    ai_accuracy: float = Field(..., description="AI 정확도(승률, %)")
    ai_wins: int = Field(..., description="수익 거래 수")
    ai_closed_trades: int = Field(..., description="종료 거래 수")
    updated_at: str = Field(..., description="업데이트 시각")


class AIAccuracyPointResponse(BaseModel):
    """AI 정확도 포인트."""

    label: str = Field(..., description="구간 라벨")
    accuracy: float = Field(..., description="구간 정확도(승률, %)")
    wins: int = Field(..., description="구간 수익 거래 수")
    closed_trades: int = Field(..., description="구간 종료 거래 수")


class AIAccuracyHistoryResponse(BaseModel):
    """AI 정확도 히스토리 응답."""

    range: str = Field(..., description="조회 범위(day/week/month)")
    accuracy: float = Field(..., description="범위 전체 정확도(승률, %)")
    wins: int = Field(..., description="범위 전체 수익 거래 수")
    closed_trades: int = Field(..., description="범위 전체 종료 거래 수")
    points: List[AIAccuracyPointResponse] = Field(default_factory=list)
    updated_at: str = Field(..., description="업데이트 시각")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_kst_datetime(timestamp_value: Any) -> datetime | None:
    """타임스탬프를 한국시간 datetime으로 변환합니다."""
    if timestamp_value is None:
        return None
    raw = str(timestamp_value).strip()
    if not raw:
        return None

    # ISO8601 'Z' 대응
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    else:
        return dt.astimezone(KST)


def _is_today_kst(timestamp_value: Any) -> bool:
    """타임스탬프가 오늘(한국시간)인지 반환합니다."""
    dt = _parse_kst_datetime(timestamp_value)
    if dt is None:
        return False
    return dt.date() == datetime.now(KST).date()


def _apply_buy_cost_basis(
    cost_basis: Dict[str, Dict[str, float]],
    symbol: str,
    volume: float,
    amount: float,
    price: float,
    fee: float,
) -> None:
    """BUY 체결을 cost basis에 반영합니다."""
    existing = cost_basis.get(symbol, {"qty": 0.0, "avg": 0.0})
    prev_qty = existing["qty"]
    prev_avg = existing["avg"]
    prev_cost = prev_qty * prev_avg
    new_cost = amount + fee if amount > 0 else (price * volume + fee)
    total_qty = prev_qty + volume
    if total_qty <= 0:
        return
    existing["qty"] = total_qty
    existing["avg"] = (prev_cost + new_cost) / total_qty
    cost_basis[symbol] = existing


def _apply_sell_and_get_realized(
    cost_basis: Dict[str, Dict[str, float]],
    symbol: str,
    volume: float,
    amount: float,
    price: float,
    fee: float,
    pnl_krw: Any,
) -> float | None:
    """SELL 체결의 실현손익을 계산하고 cost basis를 갱신합니다."""
    existing = cost_basis.get(symbol, {"qty": 0.0, "avg": 0.0})
    avg_cost = existing["avg"]

    realized: float | None = None
    if pnl_krw is not None:
        realized = _to_float(pnl_krw, default=0.0)
    elif avg_cost > 0:
        sell_value = amount if amount > 0 else (price * volume)
        realized = (sell_value - fee) - (avg_cost * volume)

    remain_qty = max(0.0, existing["qty"] - volume)
    if remain_qty <= 0:
        cost_basis[symbol] = {"qty": 0.0, "avg": 0.0}
    else:
        cost_basis[symbol] = {"qty": remain_qty, "avg": avg_cost}

    return realized


def _calculate_ai_accuracy(history_rows: List[Dict[str, Any]]) -> Tuple[float, int, int]:
    """
    거래 이력으로 승률(정확도)을 계산합니다.

    - BUY는 심볼별 평균매수가를 갱신
    - SELL은 평균매수가 대비 실현손익 계산
    - 승률 집계는 SELL 중 '오늘(한국시간)' 건만 반영
    """
    if not history_rows:
        return 0.0, 0, 0

    rows = sorted(history_rows, key=lambda row: str(row.get("timestamp", "")))
    cost_basis: Dict[str, Dict[str, float]] = {}
    wins = 0
    closed = 0

    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        side = str(row.get("side", "")).upper()
        volume = _to_float(row.get("volume"))
        amount = _to_float(row.get("amount"))
        fee = _to_float(row.get("fee"))
        if not symbol or volume <= 0:
            continue

        price = _to_float(row.get("price"))
        if price <= 0 and volume > 0:
            price = amount / volume if amount > 0 else 0.0
        if price <= 0:
            continue

        if side == "BUY":
            _apply_buy_cost_basis(cost_basis, symbol, volume, amount, price, fee)
            continue

        if side != "SELL":
            continue

        realized = _apply_sell_and_get_realized(
            cost_basis=cost_basis,
            symbol=symbol,
            volume=volume,
            amount=amount,
            price=price,
            fee=fee,
            pnl_krw=row.get("pnl_krw"),
        )

        if _is_today_kst(row.get("timestamp")) and realized is not None:
            closed += 1
            if realized > 0:
                wins += 1

    accuracy = (wins / closed * 100.0) if closed > 0 else 0.0
    return round(accuracy, 1), wins, closed


def _build_accuracy_history(
    history_rows: List[Dict[str, Any]],
    range_key: Literal["day", "week", "month"],
) -> Tuple[List[Dict[str, Any]], float, int, int]:
    """범위별 정확도 히스토리 포인트를 생성합니다."""
    now_kst = datetime.now(KST)
    if range_key == "day":
        start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
        labels = [f"{hour:02d}:00" for hour in range(24)]
        label_fn = lambda dt: dt.strftime("%H:00")
    elif range_key == "week":
        start = (now_kst - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        labels = [(start + timedelta(days=idx)).strftime("%m-%d") for idx in range(7)]
        label_fn = lambda dt: dt.strftime("%m-%d")
    else:
        start = (now_kst - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        labels = [(start + timedelta(days=idx)).strftime("%m-%d") for idx in range(30)]
        label_fn = lambda dt: dt.strftime("%m-%d")

    buckets: Dict[str, Dict[str, int]] = {label: {"wins": 0, "closed": 0} for label in labels}

    rows = sorted(history_rows, key=lambda row: str(row.get("timestamp", "")))
    cost_basis: Dict[str, Dict[str, float]] = {}

    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        side = str(row.get("side", "")).upper()
        volume = _to_float(row.get("volume"))
        amount = _to_float(row.get("amount"))
        fee = _to_float(row.get("fee"))
        if not symbol or volume <= 0:
            continue

        price = _to_float(row.get("price"))
        if price <= 0 and volume > 0:
            price = amount / volume if amount > 0 else 0.0
        if price <= 0:
            continue

        if side == "BUY":
            _apply_buy_cost_basis(cost_basis, symbol, volume, amount, price, fee)
            continue
        if side != "SELL":
            continue

        realized = _apply_sell_and_get_realized(
            cost_basis=cost_basis,
            symbol=symbol,
            volume=volume,
            amount=amount,
            price=price,
            fee=fee,
            pnl_krw=row.get("pnl_krw"),
        )
        if realized is None:
            continue

        dt = _parse_kst_datetime(row.get("timestamp"))
        if dt is None or dt < start or dt > now_kst:
            continue

        label = label_fn(dt)
        if label not in buckets:
            continue

        buckets[label]["closed"] += 1
        if realized > 0:
            buckets[label]["wins"] += 1

    points: List[Dict[str, Any]] = []
    total_wins = 0
    total_closed = 0
    for label in labels:
        wins = buckets[label]["wins"]
        closed = buckets[label]["closed"]
        total_wins += wins
        total_closed += closed
        accuracy = (wins / closed * 100.0) if closed > 0 else 0.0
        points.append(
            {
                "label": label,
                "accuracy": round(accuracy, 1),
                "wins": wins,
                "closed_trades": closed,
            }
        )

    total_accuracy = (total_wins / total_closed * 100.0) if total_closed > 0 else 0.0
    return points, round(total_accuracy, 1), total_wins, total_closed


@router.get(
    "/ai-accuracy",
    response_model=AIAccuracyResponse,
    summary="AI 정확도(승률)",
    description="거래 이력 기반 AI 정확도(승률)를 반환합니다.",
)
async def get_ai_accuracy():
    try:
        history = await trades.get_trade_history(limit=100, symbol=None)
    except Exception:
        history = []

    ai_accuracy, ai_wins, ai_closed_trades = _calculate_ai_accuracy(history)
    return AIAccuracyResponse(
        ai_accuracy=ai_accuracy,
        ai_wins=ai_wins,
        ai_closed_trades=ai_closed_trades,
        updated_at=datetime.now().isoformat(),
    )


@router.get(
    "/ai-accuracy/history",
    response_model=AIAccuracyHistoryResponse,
    summary="AI 정확도 히스토리",
    description="일별/주별/월별 AI 정확도 이력 포인트를 반환합니다.",
)
async def get_ai_accuracy_history(
    range: Literal["day", "week", "month"] = Query(default="day"),
):
    try:
        history = await trades.get_trade_history(limit=100, symbol=None)
    except Exception:
        history = []

    points, accuracy, wins, closed_trades = _build_accuracy_history(history, range)
    return AIAccuracyHistoryResponse(
        range=range,
        accuracy=accuracy,
        wins=wins,
        closed_trades=closed_trades,
        points=points,
        updated_at=datetime.now().isoformat(),
    )


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="대시보드 요약",
    description="포트폴리오/추천코인 핵심 정보를 한 번에 반환합니다.",
)
async def get_dashboard_overview():
    """대시보드 메인 요약 데이터."""

    balance = await trades.get_balance()
    positions = await trades.get_positions()
    try:
        history = await trades.get_trade_history(limit=100, symbol=None)
    except Exception:
        history = []
    try:
        score_rows = await coins.get_coin_scores()
    except Exception:
        score_rows = []
    ai_accuracy, ai_wins, ai_closed_trades = _calculate_ai_accuracy(history)

    top = []
    for row in score_rows[:4]:
        top.append(
            {
                "symbol": row.get("symbol"),
                "total_score": row.get("total_score"),
                "signal": row.get("signal"),
                "current_price": row.get("current_price"),
            }
        )

    return DashboardOverviewResponse(
        total_value=balance.total_value,
        available_krw=balance.available_krw,
        positions_count=len(positions),
        ai_accuracy=ai_accuracy,
        ai_wins=ai_wins,
        ai_closed_trades=ai_closed_trades,
        top_recommendations=top,
        updated_at=datetime.now().isoformat(),
    )
