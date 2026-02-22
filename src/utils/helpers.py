"""유틸리티 함수"""

import os
import yaml
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import ccxt
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

KST = ZoneInfo("Asia/Seoul")


def load_config(path: str = "config/settings.yaml") -> dict:
    """YAML 설정 파일 로드"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_kst() -> datetime:
    """현재 한국 시간"""
    return datetime.now(KST)


def is_trading_session(config: dict) -> bool:
    """현재 시간이 매매 세션 내인지 확인"""
    schedule_cfg = config.get("schedule", {})
    if bool(schedule_cfg.get("always_on", False)):
        return True

    current = now_kst()
    current_time = current.strftime("%H:%M")
    sessions = schedule_cfg.get("sessions", [])

    def _in_session(start: str, end: str, now_hhmm: str) -> bool:
        # 자정을 넘지 않는 세션
        if start <= end:
            return start <= now_hhmm <= end
        # 자정을 넘는 세션 (예: 16:00~00:00, 22:00~06:00)
        return now_hhmm >= start or now_hhmm <= end

    for session in sessions:
        start = session["start"]
        end = session["end"]
        if _in_session(start, end, current_time):
            # 세션 종료 N분 전 신규 진입 차단 체크
            no_entry_min = int(schedule_cfg.get("no_entry_before_end_minutes", 15))
            if no_entry_min <= 0:
                return True

            now_dt = current.replace(second=0, microsecond=0)
            end_dt = current.replace(
                hour=int(end[:2]),
                minute=int(end[3:5]),
                second=0,
                microsecond=0,
            )
            if start > end and current_time >= start:
                end_dt += timedelta(days=1)

            cutoff_dt = end_dt - timedelta(minutes=no_entry_min)
            if now_dt <= cutoff_dt:
                return True

            logger.debug(f"세션 종료 {no_entry_min}분 전 — 신규 진입 차단")
            return False
    return False


def format_krw(amount: float) -> str:
    """KRW 금액 포맷팅 (레거시 호환)"""
    return f"{amount:,.0f} KRW"


def format_usdt(amount: float) -> str:
    """USDT 금액 포맷팅"""
    if abs(amount) >= 1:
        return f"{amount:,.2f} USDT"
    return f"{amount:.4f} USDT"


def format_pct(value: float) -> str:
    """퍼센트 포맷팅"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def get_env(key: str, default=None):
    """환경변수 가져오기"""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"환경변수 {key}가 설정되지 않았습니다.")
    return value


def get_okx_credentials(mode: str = "live") -> dict:
    """모드별 OKX API 자격증명 조회"""
    mode = (mode or "").lower().strip()

    if mode == "demo":
        return {
            "apiKey": get_env("OKX_DEMO_API_KEY"),
            "secret": get_env("OKX_DEMO_SECRET_KEY"),
            "password": get_env("OKX_DEMO_PASSPHRASE"),
        }

    if mode == "live":
        return {
            "apiKey": get_env("OKX_API_KEY"),
            "secret": get_env("OKX_SECRET_KEY"),
            "password": get_env("OKX_PASSPHRASE"),
        }

    return {}


def create_okx_exchange(mode: str = "paper") -> ccxt.okx:
    """모드별 OKX exchange 인스턴스 생성"""
    mode = (mode or "").lower().strip()
    params = {"enableRateLimit": True}

    if mode in ("live", "demo"):
        params.update(get_okx_credentials(mode))

    exchange = ccxt.okx(params)

    if mode == "demo":
        # OKX 데모 트레이딩 헤더(x-simulated-trading: 1) 자동 적용
        exchange.set_sandbox_mode(True)

    return exchange


def generate_trade_id(pair: str) -> str:
    """고유 거래 ID 생성"""
    ts = now_kst().strftime("%Y%m%d%H%M%S%f")
    # OKX 심볼의 /와 : 를 제거하여 ID에 사용
    clean_pair = pair.replace("/", "").replace(":", "_")
    return f"{clean_pair}_{ts}"


def symbol_to_base(pair: str) -> str:
    """OKX 심볼에서 기초자산 이름 추출

    'BTC/USDT:USDT' -> 'BTC'
    'ETH/USDT' -> 'ETH'
    """
    return pair.split("/")[0]
