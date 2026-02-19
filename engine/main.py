"""
CryptoAI Master — 자동매매 엔진 엔트리포인트
==============================================

24시간 무인 자동매매 시스템의 메인 실행 파일입니다.

Usage:
    # 모의투자 모드 (기본)
    $ python -m engine.main

    # 실전 모드 (⚠️ 실제 돈이 움직입니다!)
    $ TRADING_MODE=live python -m engine.main

    # 모의투자 + 즉시 1회 스코어링/매수 테스트
    $ python -m engine.main --test-run
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# ─── 로깅 설정 ───

LOG_FORMAT = (
    "%(asctime)s │ %(levelname)-7s │ %(name)-25s │ %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            f"engine_log_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8",
        ),
    ],
)

logger = logging.getLogger("engine.main")
# httpx INFO 로그에 webhook URL이 노출될 수 있어 경고 이상만 출력
logging.getLogger("httpx").setLevel(logging.WARNING)


def _persist_total_budget_to_env(new_budget: int) -> None:
    """shared/.env의 TOTAL_BUDGET 값을 업데이트합니다."""
    env_path = os.environ.get("TOTAL_BUDGET_ENV_FILE", "/app/shared/.env")
    if not os.path.exists(env_path):
        logger.warning("[예산 동기화] .env 파일을 찾을 수 없어 파일 갱신을 건너뜁니다: %s", env_path)
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        updated = False
        for i, line in enumerate(lines):
            if line.lstrip().startswith("TOTAL_BUDGET="):
                comment = ""
                if "#" in line:
                    comment = "  #" + line.split("#", 1)[1].strip()
                lines[i] = f"TOTAL_BUDGET={new_budget}{comment}\n"
                updated = True
                break

        if not updated:
            lines.append(f"\nTOTAL_BUDGET={new_budget}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info("[예산 동기화] .env TOTAL_BUDGET 갱신 완료: ₩%s", f"{new_budget:,.0f}")
    except Exception as e:
        logger.warning("[예산 동기화] .env 파일 갱신 실패: %s", e)


# ═══════════════════════════════════════════════════
# 개발용 인메모리 클래스
# ═══════════════════════════════════════════════════

class InMemoryDBManager:
    """개발용 인메모리 DB 매니저.

    모의투자 잔고와 포지션을 메모리에 저장합니다.
    """

    def __init__(self, initial_balance: float = 1_000_000) -> None:
        self._balance = initial_balance
        self._positions: List[Dict[str, Any]] = []
        self._trades: List[Dict[str, Any]] = []
        self._scoring_results: List[Any] = []
        self._feedbacks: List[Dict[str, Any]] = []

    # ── 스코어링 ──
    def get_latest_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """임시 기술지표 데이터를 반환합니다."""
        import random
        base_prices = {
            "BTC": 143_000_000, "ETH": 4_800_000,
            "XRP": 3_500, "SOL": 285_000,
        }
        price = base_prices.get(symbol, 100_000)
        noise = random.uniform(0.97, 1.03)
        current = price * noise

        return {
            "current_price": current,
            "open_price": price,
            "rsi_14": random.uniform(20, 80),
            "macd_histogram": random.uniform(-500, 500) * (price / 100_000),
            "macd_signal": random.uniform(-300, 300) * (price / 100_000),
            "bollinger_lower": current * 0.97,
            "bollinger_upper": current * 1.03,
            "sma_5": current * random.uniform(0.99, 1.01),
            "sma_20": current * random.uniform(0.98, 1.02),
            "sma_60": current * random.uniform(0.97, 1.03),
            "ema_12": current * random.uniform(0.99, 1.01),
            "ema_26": current * random.uniform(0.99, 1.01),
            "adx": random.uniform(15, 45),
            "stoch_k": random.uniform(10, 90),
            "stoch_d": random.uniform(15, 85),
            "roc_12": random.uniform(-8, 8),
            "cci_20": random.uniform(-200, 200),
            "volume_ratio": random.uniform(0.5, 3.0),
            "obv_trend": random.choice(["RISING", "NEUTRAL", "FALLING"]),
            "vwap": current * random.uniform(0.99, 1.01),
        }

    def get_latest_volatility(self, symbol: str) -> Optional[Dict[str, Any]]:
        import random
        return {
            "volatility_regime": random.choice(["LOW", "MEDIUM", "HIGH"]),
            "atr_percent": random.uniform(0.5, 5.0),
            "bb_width": random.uniform(0.01, 0.08),
        }

    def get_latest_sentiment(self) -> Optional[Dict[str, Any]]:
        import random
        return {
            "fear_greed_index": random.randint(15, 85),
            "news_sentiment": random.uniform(-0.5, 0.5),
            "social_volume_change": random.uniform(-30, 80),
        }

    def insert_scoring_result(self, result: Any) -> None:
        self._scoring_results.append(result)

    # ── 주문/포지션 ──
    def insert_trade_order(self, order: Dict[str, Any]) -> None:
        order["id"] = len(self._trades) + 1
        self._trades.append(order)
        logger.debug("[InMemoryDB] 거래 기록 저장: %s", order.get("symbol"))

    def upsert_position(self, position: Dict[str, Any]) -> None:
        existing = next(
            (p for p in self._positions if p["symbol"] == position["symbol"]),
            None,
        )
        if existing:
            existing.update(position)
        else:
            self._positions.append(position)

    def close_position(self, symbol: str) -> None:
        self._positions = [p for p in self._positions if p["symbol"] != symbol]

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return [p for p in self._positions if p.get("status") == "OPEN"]

    def get_paper_balance(self) -> Dict[str, Any]:
        coins = {}
        for p in self._positions:
            if p.get("status") == "OPEN":
                coins[p["symbol"]] = {
                    "balance": p.get("volume", 0),
                    "avg_buy_price": p.get("avg_buy_price", 0),
                }
        return {"KRW": self._balance, "coins": coins}

    def update_paper_balance(self, delta_krw: float) -> None:
        self._balance += delta_krw

    def get_today_trades(self) -> List[Dict[str, Any]]:
        today = datetime.now().date()
        return [
            t for t in self._trades
            if isinstance(t.get("filled_at"), datetime)
            and t["filled_at"].date() == today
        ]

    def get_daily_performance(self, date: Any) -> Dict[str, Any]:
        return {
            "date": str(date),
            "total_pnl_krw": 0,
            "total_trades": len(self.get_today_trades()),
            "win_rate": 0.0,
        }

    def save_llm_feedback(self, feedback: Dict[str, Any]) -> None:
        self._feedbacks.append(feedback)


class LoggingDiscordNotifier:
    """웹훅 미설정 시 로그만 남기는 알림기."""

    def send_trade_alert(self, data: Dict[str, Any]) -> None:
        logger.info("📢 [Discord] 매매 알림: %s %s ₩%s",
                     data.get("side"), data.get("symbol"),
                     f"{data.get('total_krw', 0):,.0f}")

    def send_risk_alert(self, action: Any) -> None:
        logger.info("⚠️ [Discord] 리스크 알림: %s", action)

    def send_scoring_report(self, results: List[Any]) -> None:
        symbols = [f"{r.symbol}({r.total_score:.0f})" for r in results[:4]]
        logger.info("📊 [Discord] 스코어링 리포트: %s", " | ".join(symbols))

    def send_error_alert(self, message: str) -> None:
        logger.error("🚨 [Discord] 에러: %s", message)

    def send_system_alert(self, message: str) -> None:
        logger.info("🤖 [Discord] 시스템: %s", message)


# ═══════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════

def create_engine(
    trading_mode: str = "paper",
    initial_balance: float = 1_000_000,
) -> "TradingScheduler":
    """자동매매 엔진 인스턴스를 생성합니다.

    Args:
        trading_mode: "paper" 또는 "live".
        initial_balance: 모의투자 초기 잔고.

    Returns:
        TradingScheduler 인스턴스.
    """
    from engine.config.settings import get_settings
    from engine.layer4_execution.order_manager import OrderManager
    from engine.layer4_execution.risk_manager import RiskManager
    from engine.notifications.discord_notifier import DiscordNotifier
    from engine.scheduler.cron_jobs import TradingScheduler

    # 설정 로드
    try:
        settings = get_settings()
    except Exception:
        # 설정 로드 실패 시 기본값 사용
        logger.warning("설정 로드 실패 → 기본값 사용")

        class FallbackSettings:
            # trading_mode = trading_mode  <-- 삭제 (인스턴스 속성으로 설정됨)
            def __init__(self):
                self.trading_mode = trading_mode
                self.upbit_api_key = ""
                self.upbit_secret_key = ""
                self.stop_loss_pct = -3.0
                self.take_profit_pct = 5.0
                self.total_budget = int(initial_balance)
                self.budget_ratio = 0.7

        settings = FallbackSettings()

    # 개발용 인메모리 DB
    db = InMemoryDBManager(initial_balance=initial_balance)

    # 주문 매니저
    order_mgr = OrderManager(db_manager=db, settings=settings)

    # live 모드에서는 TOTAL_BUDGET을 실계좌 KRW 잔고로 자동 동기화
    if getattr(settings, "trading_mode", "paper") == "live":
        try:
            live_balance = order_mgr.get_balance()
            live_krw = float(live_balance.get("KRW", 0))
            if live_krw > 0:
                synced_budget = max(1, int(live_krw))
                prev_budget = int(getattr(settings, "total_budget", 0))
                settings.total_budget = synced_budget
                logger.info(
                    "[예산 동기화] TOTAL_BUDGET: ₩%s → ₩%s (업비트 실잔고 기준)",
                    f"{prev_budget:,.0f}",
                    f"{synced_budget:,.0f}",
                )
                _persist_total_budget_to_env(synced_budget)
            else:
                logger.warning("[예산 동기화] 업비트 KRW 잔고가 0원이거나 조회 실패로 기존 TOTAL_BUDGET 유지")
        except Exception as e:
            logger.warning("[예산 동기화] 실잔고 조회 실패로 기존 TOTAL_BUDGET 유지: %s", e)

    # 리스크 매니저
    risk_mgr = RiskManager(
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
    )

    # Discord (웹훅이 설정되면 실제 전송기 사용)
    webhook_url = getattr(settings, "discord_webhook_url", "")
    if webhook_url and "discord.com/api/webhooks/" in webhook_url:
        discord = DiscordNotifier(webhook_url=webhook_url)
        logger.info("Discord 알림기 초기화 완료 | webhook=설정됨")
    else:
        discord = LoggingDiscordNotifier()
        logger.warning("Discord 웹훅 미설정/형식오류 → 로그 알림기로 동작")

    # 스케줄러
    scheduler = TradingScheduler(
        db_manager=db,
        order_manager=order_mgr,
        risk_manager=risk_mgr,
        discord=discord,
    )

    return scheduler


def test_run() -> None:
    """1회 테스트 실행 — 스케줄러 없이 즉시 스코어링 + 매수 사이클.

    Usage:
        $ python -m engine.main --test-run
    """
    logger.info("")
    logger.info("🧪 테스트 실행 모드 (1회성)")
    logger.info("=" * 60)

    from engine.config.settings import get_settings
    from engine.layer3_strategy.multi_factor_scoring import MultiFactorScoring
    from engine.layer3_strategy.portfolio_allocator import PortfolioAllocator
    from engine.layer4_execution.order_manager import OrderManager
    from engine.layer4_execution.risk_manager import RiskManager

    db = InMemoryDBManager(initial_balance=1_000_000)

    class FallbackSettings:
        trading_mode = "paper"
        upbit_api_key = ""
        upbit_secret_key = ""
        stop_loss_pct = -3.0
        take_profit_pct = 5.0
        total_budget = 1_000_000
        budget_ratio = 0.7

    settings = FallbackSettings()

    # 1. 스코어링
    logger.info("\n📊 [1/4] 멀티팩터 스코어링")
    logger.info("-" * 40)
    scorer = MultiFactorScoring(db_manager=db)
    results = scorer.score_all_coins(["BTC", "ETH", "XRP", "SOL"])

    for r in results:
        bar = "█" * int(r.total_score / 5) + "░" * (20 - int(r.total_score / 5))
        logger.info(
            "  [%s] %5.1f점 %s %s (신뢰도 %.0f%%)",
            r.symbol, r.total_score, bar, r.signal, r.confidence,
        )

    # 2. 매수 후보 필터
    logger.info("\n🎯 [2/4] 매수 후보 필터링")
    logger.info("-" * 40)
    buy_candidates = [r for r in results if r.signal in ("BUY", "STRONG_BUY")]
    logger.info("  매수 후보: %s", [c.symbol for c in buy_candidates] or "없음")

    if buy_candidates:
        # 3. 예산 배분
        logger.info("\n💰 [3/4] 예산 배분")
        logger.info("-" * 40)

        # 테스트용 현재가
        current_prices = {
            "BTC": 143_000_000, "ETH": 4_800_000,
            "XRP": 3_500, "SOL": 285_000,
        }

        available_krw = settings.total_budget * settings.budget_ratio
        logger.info("  투자 가능: ₩%s", f"{available_krw:,.0f}")

        allocator = PortfolioAllocator()
        allocations = allocator.allocate(available_krw, buy_candidates, current_prices)

        for alloc in allocations:
            logger.info("  %s", alloc)

        # 4. 리스크 체크 시뮬레이션
        logger.info("\n🛡️ [4/4] 리스크 체크")
        logger.info("-" * 40)
        risk_mgr = RiskManager(
            stop_loss_pct=settings.stop_loss_pct,
            take_profit_pct=settings.take_profit_pct,
        )

        # 가상 포지션
        sample_positions = [
            {
                "symbol": "BTC",
                "avg_buy_price": 145_000_000,
                "volume": 0.001,
                "opened_at": datetime.now(),
                "highest_price": 148_000_000,
            },
        ]
        actions = risk_mgr.check_positions(sample_positions, current_prices)
        for a in actions:
            logger.info("  %s", a)

    logger.info("")
    logger.info("=" * 60)
    logger.info("🧪 테스트 실행 완료!")
    logger.info("=" * 60)


def main() -> None:
    """메인 엔트리포인트.

    Usage:
        $ python -m engine.main           # 24시간 자동매매 시작
        $ python -m engine.main --test-run  # 1회 테스트
    """
    parser = argparse.ArgumentParser(
        description="CryptoAI Master — 24시간 자동매매 엔진",
    )
    parser.add_argument(
        "--test-run", action="store_true",
        help="1회 테스트 실행 (스케줄러 미사용)",
    )
    parser.add_argument(
        "--mode", choices=["paper", "live"], default="paper",
        help="투자 모드 (기본: paper)",
    )
    parser.add_argument(
        "--balance", type=float, default=1_000_000,
        help="모의투자 초기 잔고 (기본: 1,000,000)",
    )

    args = parser.parse_args()

    # 배너 출력
    print("")
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║  🤖 CryptoAI Master v1.0                 ║")
    print("  ║  24시간 무인 자동매매 시스템               ║")
    print(f"  ║  모드: {'🔴 실전투자' if args.mode == 'live' else '🧪 모의투자':<20}  ║")
    print(f"  ║  잔고: ₩{args.balance:>12,.0f}             ║")
    print("  ╚═══════════════════════════════════════════╝")
    print("")

    if args.mode == "live":
        logger.warning("⚠️  실전 투자 모드입니다! 실제 자금이 거래됩니다!")
        logger.warning("⚠️  5초 후 시작합니다... (Ctrl+C로 취소)")
        time.sleep(5)

    # 1회 테스트 모드
    if args.test_run:
        test_run()
        return

    # 24시간 자동매매 모드
    scheduler = create_engine(
        trading_mode=args.mode,
        initial_balance=args.balance,
    )

    # 종료 시그널 핸들러
    def shutdown(signum, frame):
        logger.info("종료 시그널 수신 (signal=%s)", signum)
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # 시작
    scheduler.start()

    # 무한 루프 (Ctrl+C로 종료)
    logger.info("Ctrl+C로 종료하세요.")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()


if __name__ == "__main__":
    main()
