"""시스템 API — /api/system/*"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class JobStatus(BaseModel):
    job_id: str
    name: str
    schedule: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    status: str = "configured"
    run_count: int = 0
    error_count: int = 0


class SchedulerStatus(BaseModel):
    is_running: bool
    trading_mode: str
    uptime_seconds: float
    jobs: List[JobStatus]


class SystemStatus(BaseModel):
    api_version: str
    status: str
    trading_mode: str
    trading_paused: bool = False
    uptime_seconds: float
    python_version: str
    os_info: str
    components: Dict[str, str]


class ConfigResponse(BaseModel):
    trading_mode: str
    target_coins: List[str]
    scoring_weights: Dict[str, float]
    risk_params: Dict[str, Any]
    schedule_intervals: Dict[str, str]


class LogEntry(BaseModel):
    timestamp: str
    level: str
    logger_name: str
    message: str


class PauseResponse(BaseModel):
    paused: bool
    message: str
    updated_at: str


_server_start = datetime.now()
_trading_paused = False


def _uptime() -> float:
    return (datetime.now() - _server_start).total_seconds()


def _env_minutes(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _check_database() -> str:
    try:
        from database.db_manager import DBManager

        DBManager().execute_query("SELECT 1")
        return "connected"
    except Exception:
        return "disconnected"


def _check_upbit() -> str:
    try:
        response = httpx.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": "KRW-BTC"},
            timeout=5.0,
        )
        response.raise_for_status()
        rows = response.json()
        if isinstance(rows, list) and rows:
            return "connected"
        return "error"
    except Exception:
        return "disconnected"


def _schedule_intervals() -> Dict[str, str]:
    collect = _env_minutes("DATA_COLLECTION_INTERVAL", 5)
    indicator = _env_minutes("INDICATOR_CALC_INTERVAL", 15)
    scoring = _env_minutes("SCORING_INTERVAL", 30)
    buy = _env_minutes("BUY_EXECUTION_INTERVAL", 30)
    risk = _env_minutes("RISK_CHECK_INTERVAL", 5)
    return {
        "data_collection": f"every {collect}min",
        "indicator_calc": f"every {indicator}min",
        "scoring": f"every {scoring}min",
        "execute_buy": f"every {buy}min",
        "risk_check": f"every {risk}min",
        "llm_feedback": "daily 00:30 KST",
    }


def _scheduler_jobs() -> List[JobStatus]:
    intervals = _schedule_intervals()
    return [
        JobStatus(job_id="collect_data", name="데이터 수집", schedule=intervals["data_collection"]),
        JobStatus(job_id="calc_indicators", name="지표 계산", schedule=intervals["indicator_calc"]),
        JobStatus(job_id="scoring", name="AI 스코어링", schedule=intervals["scoring"]),
        JobStatus(job_id="execute_buy", name="매수 실행", schedule=intervals["execute_buy"]),
        JobStatus(job_id="risk_check", name="리스크 체크", schedule=intervals["risk_check"]),
        JobStatus(job_id="llm_feedback", name="AI 피드백", schedule=intervals["llm_feedback"]),
    ]


@router.get("/status", response_model=SystemStatus, summary="시스템 전체 상태")
async def get_system_status():
    components = {
        "database": _check_database(),
        "scheduler": "configured",
        "upbit_api": _check_upbit(),
        "redis": "optional",
    }
    values = list(components.values())
    if all(value in ("connected", "configured", "optional") for value in values):
        status = "healthy"
    elif any(value == "error" for value in values):
        status = "error"
    else:
        status = "degraded"

    return SystemStatus(
        api_version="1.0.0",
        status=status,
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        trading_paused=_trading_paused,
        uptime_seconds=round(_uptime(), 1),
        python_version=platform.python_version(),
        os_info=f"{platform.system()} {platform.release()}",
        components=components,
    )


@router.get("/scheduler", response_model=SchedulerStatus, summary="스케줄러 상태")
async def get_scheduler_status():
    return SchedulerStatus(
        is_running=True,
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        uptime_seconds=round(_uptime(), 1),
        jobs=_scheduler_jobs(),
    )


@router.get("/config", response_model=ConfigResponse, summary="현재 설정값")
async def get_config():
    target_coins = [
        coin.strip().upper()
        for coin in os.environ.get("TARGET_COINS", "BTC,ETH,XRP,SOL").split(",")
        if coin.strip()
    ]
    return ConfigResponse(
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        target_coins=target_coins,
        scoring_weights={
            "technical": 0.30,
            "momentum": 0.25,
            "volatility": 0.15,
            "volume": 0.15,
            "sentiment": 0.15,
        },
        risk_params={
            "stop_loss_pct": float(os.environ.get("STOP_LOSS_PCT", "-3.0")),
            "take_profit_pct": float(os.environ.get("TAKE_PROFIT_PCT", "5.0")),
            "trailing_stop_pct": float(os.environ.get("TRAILING_STOP_PCT", "-2.0")),
            "max_holding_hours": int(os.environ.get("MAX_HOLDING_HOURS", "72")),
            "daily_loss_limit_pct": float(os.environ.get("DAILY_LOSS_LIMIT_PCT", "-5.0")),
        },
        schedule_intervals=_schedule_intervals(),
    )


@router.get("/logs", response_model=List[LogEntry], summary="최근 로그")
async def get_recent_logs(
    limit: int = Query(default=20, ge=1, le=50),
    level: Optional[str] = Query(default=None),
):
    _ = (limit, level)
    return []


@router.post("/pause", response_model=PauseResponse, summary="자동매매 일시정지")
async def pause_trading():
    global _trading_paused
    _trading_paused = True
    return PauseResponse(
        paused=True,
        message="자동매매가 일시정지되었습니다",
        updated_at=datetime.now().isoformat(),
    )


@router.post("/resume", response_model=PauseResponse, summary="자동매매 재개")
async def resume_trading():
    global _trading_paused
    _trading_paused = False
    return PauseResponse(
        paused=False,
        message="자동매매가 재개되었습니다",
        updated_at=datetime.now().isoformat(),
    )
