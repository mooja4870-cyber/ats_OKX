"""
시스템 API — /api/system/*

■ 엔드포인트:
    GET /api/system/status     → 시스템 전체 상태
    GET /api/system/scheduler  → 스케줄러 잡 상태
    GET /api/system/config     → 현재 설정값
    GET /api/system/logs       → 최근 로그 (제한)
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import platform
import os

logger = logging.getLogger("cryptoai.api.system")

router = APIRouter()


# ════════════════════════════════════════════════════
# Pydantic 스키마
# ════════════════════════════════════════════════════

class JobStatus(BaseModel):
    """스케줄러 잡 상태"""

    job_id: str
    name: str = Field(..., description="잡 표시명")
    schedule: str = Field(..., description="크론 스케줄", examples=["every 1h"])
    last_run: Optional[str] = Field(None, description="마지막 실행 시각")
    next_run: Optional[str] = Field(None, description="다음 실행 예정 시각")
    status: str = Field(..., description="idle | running | error")
    run_count: int = Field(0, description="누적 실행 횟수")
    error_count: int = Field(0, description="누적 에러 횟수")


class SchedulerStatus(BaseModel):
    """스케줄러 전체 상태"""

    is_running: bool
    trading_mode: str = Field(..., description="paper | live")
    uptime_seconds: float
    jobs: List[JobStatus]


class SystemStatus(BaseModel):
    """시스템 전체 상태"""

    api_version: str
    status: str = Field(..., description="healthy | degraded | error")
    trading_mode: str
    uptime_seconds: float
    python_version: str
    os_info: str
    components: Dict[str, str] = Field(
        ...,
        description="컴포넌트별 상태",
        examples=[{"database": "connected", "scheduler": "running"}],
    )


class ConfigResponse(BaseModel):
    """설정값 응답 (민감 정보 제외)"""

    trading_mode: str
    target_coins: List[str]
    scoring_weights: Dict[str, float]
    risk_params: Dict[str, Any]
    schedule_intervals: Dict[str, str]


class LogEntry(BaseModel):
    """로그 항목"""

    timestamp: str
    level: str
    logger_name: str
    message: str


# ════════════════════════════════════════════════════
# 서버 시작 시각 기록
# ════════════════════════════════════════════════════

_server_start = datetime.now()


def _uptime() -> float:
    return (datetime.now() - _server_start).total_seconds()


# ════════════════════════════════════════════════════
# Mock 데이터
# ════════════════════════════════════════════════════

def _mock_scheduler_status() -> dict:
    """Mock 스케줄러 상태"""
    now_iso = datetime.now().isoformat()
    return {
        "is_running": True,
        "trading_mode": "paper",
        "uptime_seconds": _uptime(),
        "jobs": [
            {
                "job_id": "data_collection",
                "name": "📥 데이터 수집",
                "schedule": "every 1h",
                "last_run": now_iso,
                "next_run": now_iso,
                "status": "idle",
                "run_count": 24,
                "error_count": 0,
            },
            {
                "job_id": "indicator_calc",
                "name": "📊 지표 계산",
                "schedule": "every 1h (수집 후 5분)",
                "last_run": now_iso,
                "next_run": now_iso,
                "status": "idle",
                "run_count": 24,
                "error_count": 1,
            },
            {
                "job_id": "scoring",
                "name": "🧠 AI 스코어링",
                "schedule": "every 1h (지표 후 5분)",
                "last_run": now_iso,
                "next_run": now_iso,
                "status": "idle",
                "run_count": 24,
                "error_count": 0,
            },
            {
                "job_id": "execute_buy",
                "name": "💰 매수 실행",
                "schedule": "every 4h",
                "last_run": now_iso,
                "next_run": now_iso,
                "status": "idle",
                "run_count": 6,
                "error_count": 0,
            },
            {
                "job_id": "risk_check",
                "name": "🛡️ 리스크 체크",
                "schedule": "every 5min",
                "last_run": now_iso,
                "next_run": now_iso,
                "status": "idle",
                "run_count": 288,
                "error_count": 2,
            },
            {
                "job_id": "llm_feedback",
                "name": "📝 LLM 피드백",
                "schedule": "daily 09:00 KST",
                "last_run": now_iso,
                "next_run": now_iso,
                "status": "idle",
                "run_count": 1,
                "error_count": 0,
            },
        ],
    }


def _check_component(name: str) -> str:
    """컴포넌트 상태 확인"""
    if name == "database":
        try:
            from database.db_manager import DBManager
            DBManager()
            return "connected"
        except Exception:
            return "disconnected (mock mode)"
    elif name == "scheduler":
        return "running (mock)"
    elif name == "upbit_api":
        try:
            import pyupbit
            p = pyupbit.get_current_price("KRW-BTC")
            return "connected" if p else "error"
        except Exception:
            return "disconnected"
    elif name == "redis":
        return "disconnected (optional)"
    return "unknown"


# ════════════════════════════════════════════════════
# 엔드포인트
# ════════════════════════════════════════════════════

@router.get(
    "/status",
    response_model=SystemStatus,
    summary="시스템 전체 상태",
    description="API 서버, DB, 스케줄러 등 전체 시스템 상태를 반환합니다.",
)
async def get_system_status():
    """시스템 전체 상태"""

    components = {
        "database": _check_component("database"),
        "scheduler": _check_component("scheduler"),
        "upbit_api": _check_component("upbit_api"),
        "redis": _check_component("redis"),
    }

    # 전체 상태 결정
    comp_values = list(components.values())
    if all("connected" in v or "running" in v for v in comp_values):
        status = "healthy"
    elif any("error" in v for v in comp_values):
        status = "error"
    else:
        status = "degraded"

    return SystemStatus(
        api_version="1.0.0",
        status=status,
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        uptime_seconds=round(_uptime(), 1),
        python_version=platform.python_version(),
        os_info=f"{platform.system()} {platform.release()}",
        components=components,
    )


@router.get(
    "/scheduler",
    response_model=SchedulerStatus,
    summary="스케줄러 상태",
    description="APScheduler 잡 목록과 실행 통계를 반환합니다.",
)
async def get_scheduler_status():
    """스케줄러 잡 상태"""

    # TODO: 실제 TradingScheduler.get_stats() 연동
    return _mock_scheduler_status()


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="현재 설정값",
    description="민감 정보(API 키 등)를 제외한 현재 설정을 반환합니다.",
)
async def get_config():
    """현재 설정값 (민감 정보 제외)"""

    return ConfigResponse(
        trading_mode=os.environ.get("TRADING_MODE", "paper"),
        target_coins=["BTC", "ETH", "XRP", "SOL"],
        scoring_weights={
            "technical": 0.30,
            "momentum": 0.25,
            "volatility": 0.15,
            "volume": 0.15,
            "sentiment": 0.15,
        },
        risk_params={
            "stop_loss_pct": -3.0,
            "take_profit_pct": 5.0,
            "trailing_stop_pct": -2.0,
            "max_holding_hours": 72,
            "daily_loss_limit_pct": -5.0,
        },
        schedule_intervals={
            "data_collection": "every 1h",
            "indicator_calc": "every 1h (수집 후 5분)",
            "scoring": "every 1h (지표 후 5분)",
            "execute_buy": "every 4h",
            "risk_check": "every 5min",
            "llm_feedback": "daily 09:00 KST",
        },
    )


@router.get(
    "/logs",
    response_model=List[LogEntry],
    summary="최근 로그",
    description="최근 시스템 로그를 반환합니다 (최대 50건).",
)
async def get_recent_logs(
    limit: int = Query(default=20, ge=1, le=50, description="조회 건수"),
    level: Optional[str] = Query(default=None, description="레벨 필터 (INFO/WARNING/ERROR)"),
):
    """최근 로그"""

    # TODO: 실제 로그 파일/DB에서 조회
    mock_logs = [
        {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "logger_name": "cryptoai.scheduler",
            "message": "[스코어링] BTC: 82.3점 (STRONG_BUY), ETH: 64.1점 (BUY)",
        },
        {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "logger_name": "cryptoai.order",
            "message": "[매수] BTC ₩100,000 LIMIT 주문 접수 (가격: ₩143,100,000)",
        },
        {
            "timestamp": datetime.now().isoformat(),
            "level": "WARNING",
            "logger_name": "cryptoai.risk",
            "message": "[리스크] SOL 트레일링 스탑 -1.8% 접근 중 (현재: -1.5%)",
        },
        {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "logger_name": "cryptoai.data",
            "message": "[데이터] BTC 1h 캔들 168개 수집 완료 (7일)",
        },
        {
            "timestamp": datetime.now().isoformat(),
            "level": "ERROR",
            "logger_name": "cryptoai.upbit",
            "message": "[API] 업비트 요청 타임아웃 (5s) — 재시도 1/3",
        },
    ]

    if level:
        mock_logs = [l for l in mock_logs if l["level"] == level.upper()]

    return mock_logs[:limit]
