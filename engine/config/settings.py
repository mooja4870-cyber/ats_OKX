"""
CryptoAI Master — 환경 설정
============================

pydantic-settings 기반 환경변수 로드.
.env 파일 또는 시스템 환경변수에서 설정을 읽어옵니다.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """앱 전역 설정.

    환경변수 또는 .env 파일에서 자동 로드됩니다.
    """

    # ─── 업비트 API ───
    upbit_api_key: str = ""
    upbit_secret_key: str = ""
    trading_mode: str = Field(default="paper", description="paper | live")

    # ─── 타겟 코인 ───
    target_coins: str = "BTC,ETH,XRP,SOL"

    # ─── 투자금 ───
    total_budget: int = 1_000_000
    budget_ratio: float = 0.7

    # ─── Supabase / DB ───
    supabase_url: str = ""
    supabase_anon_key: str = ""
    database_url: str = ""

    # ─── Redis ───
    redis_url: str = "redis://localhost:6379"

    # ─── OpenAI ───
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # ─── Discord ───
    discord_webhook_url: str = ""

    # ─── 리스크 ───
    stop_loss_pct: float = -3.0
    take_profit_pct: float = 5.0
    trailing_stop_pct: float = -2.0
    max_holding_hours: int = 72
    daily_loss_limit_pct: float = -5.0

    # ─── 스케줄링 ───
    ohlcv_interval_min: int = 5
    scoring_interval_min: int = 30
    data_collection_interval: int = 60
    scoring_interval: int = 60
    buy_execution_interval: int = 240
    risk_check_interval: int = 5

    # ─── API ───
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    jwt_secret_key: str = "change-me-in-production"
    
    # ─── 프론트엔드 (Docker 호환용) ───
    next_public_api_url: Optional[str] = None
    next_public_ws_url: Optional[str] = None

    # ─── 스코어링 가중치 ───
    weight_technical: float = 0.30
    weight_momentum: float = 0.25
    weight_volatility: float = 0.15
    weight_volume: float = 0.15
    weight_sentiment: float = 0.15

    # ─── 스코어링 임계값 ───
    buy_threshold: float = 70.0
    strong_buy_threshold: float = 80.0
    sell_threshold: float = 30.0

    @property
    def coins_list(self) -> List[str]:
        """타겟 코인을 리스트로 반환합니다."""
        return [c.strip().upper() for c in self.target_coins.split(",")]

    @property
    def scoring_weights(self) -> dict[str, float]:
        """스코어링 가중치 딕셔너리를 반환합니다."""
        return {
            "technical": self.weight_technical,
            "momentum": self.weight_momentum,
            "volatility": self.weight_volatility,
            "volume": self.weight_volume,
            "sentiment": self.weight_sentiment,
        }

    @property
    def investable_budget(self) -> float:
        """실제 투자 가능 금액 (KRW)."""
        return self.total_budget * self.budget_ratio

    model_config = {
        "env_file": "shared/.env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# 싱글턴 패턴
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """전역 Settings 인스턴스를 반환합니다."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
