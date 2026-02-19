"""전략 API — /api/strategies/*"""

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class StrategyWeights(BaseModel):
    technical: float = Field(0.30, ge=0, le=1)
    momentum: float = Field(0.25, ge=0, le=1)
    volatility: float = Field(0.15, ge=0, le=1)
    volume: float = Field(0.15, ge=0, le=1)
    sentiment: float = Field(0.15, ge=0, le=1)


class StrategyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    description: str = Field(default="")
    weights: StrategyWeights = Field(default_factory=StrategyWeights)


class Strategy(StrategyIn):
    id: int
    is_active: bool = False
    created_at: str
    updated_at: str


_strategies: Dict[int, Strategy] = {
    1: Strategy(
        id=1,
        name="기본 전략",
        description="기본 멀티팩터 가중치 전략",
        weights=StrategyWeights(),
        is_active=True,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
}


@router.get("", response_model=List[Strategy], summary="전략 목록")
async def list_strategies():
    return sorted(_strategies.values(), key=lambda s: s.id)


@router.post("", response_model=Strategy, summary="전략 생성")
async def create_strategy(body: StrategyIn):
    next_id = max(_strategies.keys(), default=0) + 1
    now = datetime.now().isoformat()
    row = Strategy(
        id=next_id,
        name=body.name,
        description=body.description,
        weights=body.weights,
        is_active=False,
        created_at=now,
        updated_at=now,
    )
    _strategies[next_id] = row
    return row


@router.get("/{strategy_id}", response_model=Strategy, summary="전략 단건")
async def get_strategy(strategy_id: int):
    row = _strategies.get(strategy_id)
    if not row:
        raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")
    return row


@router.put("/{strategy_id}", response_model=Strategy, summary="전략 수정")
async def update_strategy(strategy_id: int, body: StrategyIn):
    row = _strategies.get(strategy_id)
    if not row:
        raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

    updated = row.model_copy(
        update={
            "name": body.name,
            "description": body.description,
            "weights": body.weights,
            "updated_at": datetime.now().isoformat(),
        }
    )
    _strategies[strategy_id] = updated
    return updated


@router.post("/{strategy_id}/activate", response_model=Strategy, summary="전략 활성화")
async def activate_strategy(strategy_id: int):
    if strategy_id not in _strategies:
        raise HTTPException(status_code=404, detail="전략을 찾을 수 없습니다")

    now = datetime.now().isoformat()
    for key, strategy in list(_strategies.items()):
        _strategies[key] = strategy.model_copy(update={"is_active": key == strategy_id, "updated_at": now})

    return _strategies[strategy_id]
