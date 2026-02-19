"""
CryptoAI Master — 24시간 자동매매 스케줄러
==========================================

APScheduler를 사용하여 5분/15분/30분/1시간 주기로 작업을 실행합니다.

작업 스케줄:
    ┌────────────┬─────────────────────────┬─────────────────┐
    │ 주기       │ 작업                    │ 설명             │
    ├────────────┼─────────────────────────┼─────────────────┤
    │ 5분마다    │ collect_data            │ OHLCV 캔들 수집  │
    │ 5분마다    │ risk_check              │ 손절/익절 체크   │
    │ 15분마다   │ calc_indicators         │ 기술지표 계산    │
    │ 30분마다   │ scoring                 │ AI 스코어링      │
    │ :00, :30   │ execute_buy             │ 매수 실행        │
    │ 00:30      │ llm_feedback            │ GPT-4o 피드백    │
    └────────────┴─────────────────────────┴─────────────────┘

Usage:
    >>> scheduler = TradingScheduler(db, order_mgr, risk_mgr, discord)
    >>> scheduler.start()
    >>> # ... Ctrl+C 시 ...
    >>> scheduler.stop()
"""

from __future__ import annotations

import logging
import os
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# 프로토콜
# ═══════════════════════════════════════════════════

class SchedulerDBProtocol(Protocol):
    """스케줄러가 사용하는 DB 인터페이스."""

    def get_latest_indicators(self, symbol: str) -> Optional[Dict[str, Any]]: ...
    def get_latest_volatility(self, symbol: str) -> Optional[Dict[str, Any]]: ...
    def get_latest_sentiment(self) -> Optional[Dict[str, Any]]: ...
    def insert_scoring_result(self, result: Any) -> None: ...
    def get_open_positions(self) -> List[Dict[str, Any]]: ...
    def get_paper_balance(self) -> Dict[str, Any]: ...
    def update_paper_balance(self, delta: float) -> None: ...
    def get_today_trades(self) -> List[Dict[str, Any]]: ...
    def get_daily_performance(self, date: Any) -> Dict[str, Any]: ...
    def save_llm_feedback(self, feedback: Dict[str, Any]) -> None: ...


class DiscordProtocol(Protocol):
    """Discord 알림 인터페이스."""

    def send_trade_alert(self, data: Dict[str, Any]) -> None: ...
    def send_risk_alert(self, data: Any) -> None: ...
    def send_scoring_report(self, results: List[Any]) -> None: ...
    def send_error_alert(self, message: str) -> None: ...
    def send_system_alert(self, message: str) -> None: ...


# ═══════════════════════════════════════════════════
# 메인 스케줄러
# ═══════════════════════════════════════════════════

class TradingScheduler:
    """24시간 자동 작동 크론잡 스케줄러.

    APScheduler BackgroundScheduler를 래핑하여 자동매매에 필요한
    6개 크론잡을 관리합니다.

    Args:
        db_manager: DB 매니저.
        order_manager: 주문 실행 매니저.
        risk_manager: 리스크 매니저.
        discord: Discord 알림기.
        target_coins: 대상 코인 리스트. 기본 ["BTC", "ETH", "XRP", "SOL"].
        paused: 초기 일시정지 여부.

    Example:
        >>> scheduler = TradingScheduler(db, order_mgr, risk_mgr, discord)
        >>> scheduler.start()
        === CryptoAI 자동매매 엔진 시작 ===
    """

    def __init__(
        self,
        db_manager: SchedulerDBProtocol,
        order_manager: Any,
        risk_manager: Any,
        discord: Optional[DiscordProtocol] = None,
        target_coins: Optional[List[str]] = None,
        paused: bool = False,
    ) -> None:
        self.db = db_manager
        self.order_mgr = order_manager
        self.risk_mgr = risk_manager
        self.discord = discord
        self.target_coins = target_coins or ["BTC", "ETH", "XRP", "SOL"]
        self.paused = paused
        self.collect_interval_min = self._env_minutes("DATA_COLLECTION_INTERVAL", 5)
        self.indicator_interval_min = self._env_minutes("INDICATOR_CALC_INTERVAL", 15)
        self.scoring_interval_min = self._env_minutes("SCORING_INTERVAL", 30)
        self.buy_interval_min = self._env_minutes("BUY_EXECUTION_INTERVAL", 30)
        self.risk_interval_min = self._env_minutes("RISK_CHECK_INTERVAL", 5)

        # 실행 통계
        self.stats: Dict[str, Dict[str, Any]] = {
            "collect_data": {"runs": 0, "errors": 0, "last_run": None},
            "calc_indicators": {"runs": 0, "errors": 0, "last_run": None},
            "scoring": {"runs": 0, "errors": 0, "last_run": None},
            "execute_buy": {"runs": 0, "errors": 0, "last_run": None},
            "risk_check": {"runs": 0, "errors": 0, "last_run": None},
            "llm_feedback": {"runs": 0, "errors": 0, "last_run": None},
        }

        # 스케줄러 생성
        self.scheduler = BackgroundScheduler(
            timezone="Asia/Seoul",
            job_defaults={
                "coalesce": True,           # 밀린 작업은 1회만 실행
                "max_instances": 1,          # 동시 실행 방지
                "misfire_grace_time": 60,    # 1분 지연까지 허용
            },
        )

        # 이벤트 리스너 등록
        self.scheduler.add_listener(
            self._on_job_executed, EVENT_JOB_EXECUTED
        )
        self.scheduler.add_listener(
            self._on_job_error, EVENT_JOB_ERROR
        )

        self._register_jobs()

        logger.info(
            "TradingScheduler 초기화 완료 | 코인=%s | paused=%s | 수집=%d분 | 지표=%d분 | 스코어=%d분 | 매수=%d분 | 리스크=%d분",
            self.target_coins,
            self.paused,
            self.collect_interval_min,
            self.indicator_interval_min,
            self.scoring_interval_min,
            self.buy_interval_min,
            self.risk_interval_min,
        )

    @staticmethod
    def _env_minutes(name: str, default: int) -> int:
        """분 단위 환경변수 값을 읽고 최소 1분으로 보정합니다."""
        raw = os.environ.get(name)
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            logger.warning("환경변수 %s=%r 파싱 실패 → 기본값 %d분 사용", name, raw, default)
            return default
        return max(1, value)

    # ─────────────────────────────────────────────
    # 크론잡 등록
    # ─────────────────────────────────────────────

    def _register_jobs(self) -> None:
        """모든 크론잡을 등록합니다."""
        jobs = [
            {
                "func": self._job_collect_data,
                "trigger": IntervalTrigger(minutes=self.collect_interval_min),
                "id": "collect_data",
                "name": f"📊 데이터 수집 ({self.collect_interval_min}분)",
            },
            {
                "func": self._job_calc_indicators,
                "trigger": IntervalTrigger(minutes=self.indicator_interval_min),
                "id": "calc_indicators",
                "name": f"📈 지표 계산 ({self.indicator_interval_min}분)",
            },
            {
                "func": self._job_scoring,
                "trigger": IntervalTrigger(minutes=self.scoring_interval_min),
                "id": "scoring",
                "name": f"🧠 AI 스코어링 ({self.scoring_interval_min}분)",
            },
            {
                "func": self._job_execute_buy,
                "trigger": IntervalTrigger(minutes=self.buy_interval_min),
                "id": "execute_buy",
                "name": f"💰 매수 실행 ({self.buy_interval_min}분)",
            },
            {
                "func": self._job_risk_check,
                "trigger": IntervalTrigger(minutes=self.risk_interval_min),
                "id": "risk_check",
                "name": f"🛡️ 리스크 체크 ({self.risk_interval_min}분)",
            },
            {
                "func": self._job_llm_feedback,
                "trigger": CronTrigger(hour=0, minute=30),
                "id": "llm_feedback",
                "name": "🤖 AI 피드백 (매일 00:30)",
            },
        ]

        for job in jobs:
            self.scheduler.add_job(
                func=job["func"],
                trigger=job["trigger"],
                id=job["id"],
                name=job["name"],
                replace_existing=True,
            )

        logger.info("크론잡 %d개 등록 완료", len(jobs))

    # ─────────────────────────────────────────────
    # 크론잡 구현
    # ─────────────────────────────────────────────

    def _job_collect_data(self) -> None:
        """[5분] OHLCV 캔들 데이터 수집.

        pyupbit를 사용하여 각 코인의 최신 OHLCV를 수집하고 DB에 저장합니다.
        """
        if self.paused:
            return

        job_id = "collect_data"
        self._update_stats(job_id)

        logger.info("[데이터 수집] 시작 | coins=%s", self.target_coins)

        try:
            import pyupbit

            for symbol in self.target_coins:
                try:
                    market = f"KRW-{symbol}"

                    # 5분봉 200개 수집
                    df = pyupbit.get_ohlcv(market, interval="minute5", count=200)

                    if df is not None and not df.empty:
                        # TODO: DB에 OHLCV 저장 (layer1_data/pipeline.py 완성 시)
                        logger.info(
                            "[데이터 수집] %s | %d봉 수집 | 최신=%s | 종가=₩%s",
                            symbol, len(df),
                            df.index[-1].strftime("%H:%M"),
                            f"{df['close'].iloc[-1]:,.0f}",
                        )
                    else:
                        logger.warning("[데이터 수집] %s | 빈 데이터", symbol)

                except Exception as e:
                    logger.error("[데이터 수집] %s | 실패: %s", symbol, e)

        except ImportError:
            logger.warning("[데이터 수집] pyupbit 미설치 → 건너뜀")

    def _job_calc_indicators(self) -> None:
        """[15분] 기술적 지표 계산.

        수집된 OHLCV 데이터에서 RSI, MACD, 볼린저밴드 등 30+ 지표를 계산합니다.
        """
        if self.paused:
            return

        job_id = "calc_indicators"
        self._update_stats(job_id)

        logger.info("[지표 계산] 시작 | coins=%s", self.target_coins)

        for symbol in self.target_coins:
            try:
                # TODO: TechnicalAnalyzer 완성 시 호출
                # from engine.layer2_analysis.technical_indicators import TechnicalAnalyzer
                # analyzer = TechnicalAnalyzer(self.db)
                # analyzer.calculate_all_indicators(symbol, "1h")
                logger.info("[지표 계산] %s | 완료", symbol)
            except Exception as e:
                logger.error("[지표 계산] %s | 실패: %s", symbol, e)

    def _job_scoring(self) -> None:
        """[30분] 멀티팩터 AI 스코어링.

        5개 팩터를 조합하여 각 코인의 0-100점 종합 점수를 산출합니다.
        STRONG_BUY / BUY / HOLD / SELL 시그널을 결정합니다.
        """
        if self.paused:
            return

        job_id = "scoring"
        self._update_stats(job_id)

        logger.info("[AI 스코어링] 시작")

        try:
            from engine.layer3_strategy.multi_factor_scoring import MultiFactorScoring

            scorer = MultiFactorScoring(db_manager=self.db)
            results = scorer.score_all_coins(self.target_coins)

            for r in results:
                logger.info(
                    "[스코어링] %s | %.1f점 | %s | 신뢰도 %.0f%%",
                    r.symbol, r.total_score, r.signal, r.confidence,
                )

            # Discord 리포트
            if self.discord:
                try:
                    self.discord.send_scoring_report(results)
                except Exception as e:
                    logger.error("[스코어링] Discord 알림 실패: %s", e)

            return results

        except Exception as e:
            logger.error("[AI 스코어링] 실패: %s", e)
            return None

    def _job_execute_buy(self) -> None:
        """[매시 :00, :30] 매수 실행 — 핵심 로직.

        Flow:
            1. 전체 코인 스코어링
            2. BUY/STRONG_BUY 후보 필터링
            3. 잔고 확인
            4. 현재가 조회
            5. 예산 배분 (PortfolioAllocator)
            6. 일일 손실 한도 체크
            7. 지정가 주문 실행
            8. Discord 알림
        """
        if self.paused:
            logger.info("[매수] 일시정지 상태 → 건너뜀")
            return

        job_id = "execute_buy"
        self._update_stats(job_id)

        logger.info("=" * 50)
        logger.info("[매수 사이클] 시작 | %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
        logger.info("=" * 50)

        try:
            from engine.layer3_strategy.multi_factor_scoring import MultiFactorScoring
            from engine.layer3_strategy.portfolio_allocator import PortfolioAllocator

            # 1. 스코어링
            scorer = MultiFactorScoring(db_manager=self.db)
            results = scorer.score_all_coins(self.target_coins)

            # 2. 매수 대상 필터
            buy_candidates = [
                r for r in results if r.signal in ("BUY", "STRONG_BUY")
            ]

            if not buy_candidates:
                logger.info("[매수] 매수 대상 없음 (전체 HOLD/SELL)")
                return

            logger.info(
                "[매수] 후보 %d개: %s",
                len(buy_candidates),
                [(c.symbol, c.total_score, c.signal) for c in buy_candidates],
            )

            # 3. 잔고 확인
            balance = self.order_mgr.get_balance()
            total_krw = balance.get("KRW", 0)

            if total_krw < 10_000:
                logger.warning("[매수] 잔고 부족: ₩%s", f"{total_krw:,.0f}")
                return

            # 4. 현재가 조회
            current_prices = self.order_mgr.get_current_prices(
                [c.symbol for c in buy_candidates]
            )

            if not current_prices:
                logger.error("[매수] 현재가 조회 실패")
                return

            # 5. 예산 배분
            allocator = PortfolioAllocator()
            allocations = allocator.allocate(total_krw, buy_candidates, current_prices)

            if not allocations:
                logger.info("[매수] 배분 결과 없음")
                return

            # 6. 일일 손실 한도 체크
            try:
                daily_trades = self.db.get_today_trades()
                daily_pnl = sum(t.get("pnl_krw", 0) for t in daily_trades)
                portfolio_value = total_krw + sum(
                    pos.get("current_value", 0)
                    for pos in self.db.get_open_positions()
                )

                if self.risk_mgr.check_daily_loss(daily_pnl, portfolio_value):
                    logger.critical("[매수] 🚨 일일 손실 한도 도달 → 매수 중단")
                    if self.discord:
                        self.discord.send_error_alert(
                            "🚨 일일 최대 손실 한도 도달! 매수를 중단합니다."
                        )
                    return
            except Exception as e:
                logger.warning("[매수] 일일 손실 체크 실패 (계속 진행): %s", e)

            # 7. 주문 실행
            for alloc in allocations:
                try:
                    result = self.order_mgr.execute_buy(
                        symbol=alloc.symbol,
                        amount=alloc.allocation_amount,
                        order_type="LIMIT",
                        limit_price=alloc.limit_price,
                        score=alloc.score,
                    )

                    if result.success and self.discord:
                        self.discord.send_trade_alert({
                            "symbol": alloc.symbol,
                            "side": "BUY",
                            "price": result.price,
                            "quantity": result.volume,
                            "total_krw": result.total_krw,
                            "score": alloc.score,
                            "signal": alloc.signal,
                        })

                    logger.info("[매수 결과] %s", result)

                except Exception as e:
                    logger.error("[매수 실패] %s: %s", alloc.symbol, e)
                    if self.discord:
                        self.discord.send_error_alert(
                            f"매수 실패: {alloc.symbol} - {e}"
                        )

        except Exception as e:
            logger.exception("[매수 사이클] 치명적 오류")
            if self.discord:
                self.discord.send_error_alert(
                    f"매수 사이클 오류: {traceback.format_exc()[:500]}"
                )

    def _job_risk_check(self) -> None:
        """[5분] 리스크 체크 — 손절/익절 자동 실행.

        모든 오픈 포지션의 PnL을 확인하고,
        손절(-3%) / 익절(+5%) / 트레일링 스탑 조건에 해당하면
        즉시 시장가 매도를 실행합니다.
        """
        if self.paused:
            return

        job_id = "risk_check"
        self._update_stats(job_id)

        try:
            positions = self.db.get_open_positions()

            if not positions:
                return  # 포지션 없으면 체크 불요

            # 현재가 조회
            symbols = [p["symbol"] for p in positions]
            current_prices = self.order_mgr.get_current_prices(symbols)

            if not current_prices:
                logger.error("[리스크] 현재가 조회 실패")
                return

            # 리스크 평가
            actions = self.risk_mgr.check_positions(positions, current_prices)

            for action in actions:
                if action.action == "HOLD":
                    continue

                logger.warning("[리스크 발동] %s", action)

                # 매도 가능 액션
                if action.action in ("STOP_LOSS", "TAKE_PROFIT", "TRAILING_STOP"):
                    pos = next(
                        (p for p in positions if p["symbol"] == action.symbol),
                        None,
                    )

                    if not pos:
                        continue

                    result = self.order_mgr.execute_sell(
                        symbol=action.symbol,
                        volume=float(pos["volume"]),
                        order_type="MARKET",
                        trigger_reason=action.action,
                    )

                    if result.success and self.discord:
                        self.discord.send_risk_alert(action)

                    logger.info(
                        "[리스크 실행] %s | %s | PnL=%+.2f%% | %s",
                        action.symbol, action.action,
                        action.pnl_pct, result,
                    )

                elif action.action == "MAX_HOLD":
                    logger.info(
                        "[리스크] %s 최대 보유 기간 초과 — 수동 확인 필요",
                        action.symbol,
                    )

        except Exception as e:
            logger.error("[리스크 체크] 오류: %s", e)

    def _job_llm_feedback(self) -> None:
        """[매일 00:30] GPT-4o 피드백 루프.

        오늘의 매매 내역과 성과를 분석하여 전략 개선 피드백을 받습니다.
        """
        if self.paused:
            return

        job_id = "llm_feedback"
        self._update_stats(job_id)

        logger.info("[AI 피드백] 매일 자정 분석 시작")

        try:
            # TODO: MarketAnalyst 완성 시 호출
            # from engine.llm_engine.market_analyst import MarketAnalyst
            #
            # analyst = MarketAnalyst()
            # trades = self.db.get_today_trades()
            # performance = self.db.get_daily_performance(datetime.now().date())
            # feedback = analyst.post_trade_analysis(trades, performance)
            # self.db.save_llm_feedback(feedback)
            # logger.info("[AI 피드백] 등급=%s", feedback.get("performance_grade"))

            logger.info("[AI 피드백] (MarketAnalyst 미구현 — 건너뜀)")

        except Exception as e:
            logger.error("[AI 피드백] 실패: %s", e)

    # ─────────────────────────────────────────────
    # 스케줄러 제어
    # ─────────────────────────────────────────────

    def start(self) -> None:
        """스케줄러를 시작합니다."""
        self.scheduler.start()

        logger.info("")
        logger.info("╔══════════════════════════════════════════════════╗")
        logger.info("║    🤖 CryptoAI Master — 자동매매 엔진 시작       ║")
        logger.info("║    모드: 24시간 무인 운전                        ║")
        logger.info("╠══════════════════════════════════════════════════╣")

        jobs = self.scheduler.get_jobs()
        for job in jobs:
            next_run = (
                job.next_run_time.strftime("%H:%M:%S")
                if job.next_run_time else "N/A"
            )
            logger.info("║  %s  다음실행=%s", f"{job.name:<32}", next_run)

        logger.info("╚══════════════════════════════════════════════════╝")
        logger.info("")

        if self.discord:
            try:
                self.discord.send_system_alert("🤖 CryptoAI 자동매매 엔진이 시작되었습니다!")
            except Exception:
                pass

    def stop(self) -> None:
        """스케줄러를 중지합니다."""
        self.scheduler.shutdown(wait=False)

        logger.info("")
        logger.info("╔══════════════════════════════════════════════════╗")
        logger.info("║    🛑 CryptoAI Master — 자동매매 엔진 종료       ║")
        logger.info("╚══════════════════════════════════════════════════╝")

        # 실행 통계 출력
        logger.info("📊 실행 통계:")
        for job_id, stat in self.stats.items():
            logger.info(
                "  [%s] 실행=%d | 오류=%d | 마지막=%s",
                job_id, stat["runs"], stat["errors"],
                stat["last_run"].strftime("%H:%M") if stat["last_run"] else "없음",
            )

        if self.discord:
            try:
                self.discord.send_system_alert("🛑 CryptoAI 자동매매 엔진이 종료되었습니다.")
            except Exception:
                pass

    def pause(self) -> None:
        """매매를 일시 정지합니다 (데이터 수집은 계속)."""
        self.paused = True
        logger.warning("⏸️  자동매매 일시정지")
        if self.discord:
            try:
                self.discord.send_system_alert("⏸️ 자동매매가 일시정지되었습니다.")
            except Exception:
                pass

    def resume(self) -> None:
        """매매를 재개합니다."""
        self.paused = False
        logger.info("▶️  자동매매 재개")
        if self.discord:
            try:
                self.discord.send_system_alert("▶️ 자동매매가 재개되었습니다.")
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """스케줄러 상태를 반환합니다.

        Returns:
            상태 딕셔너리 (API 응답용).
        """
        jobs_info = []
        for job in self.scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
            })

        return {
            "running": self.scheduler.running,
            "paused": self.paused,
            "target_coins": self.target_coins,
            "jobs": jobs_info,
            "stats": self.stats,
        }

    # ─────────────────────────────────────────────
    # 이벤트 핸들러 & 유틸리티
    # ─────────────────────────────────────────────

    def _on_job_executed(self, event: Any) -> None:
        """작업 성공 이벤트."""
        job_id = event.job_id
        if job_id in self.stats:
            self.stats[job_id]["runs"] += 1
            self.stats[job_id]["last_run"] = datetime.now()

    def _on_job_error(self, event: Any) -> None:
        """작업 실패 이벤트."""
        job_id = event.job_id
        if job_id in self.stats:
            self.stats[job_id]["errors"] += 1
            self.stats[job_id]["last_run"] = datetime.now()

        logger.error(
            "[스케줄러] 작업 오류 | job=%s | error=%s",
            job_id, event.exception,
        )

        if self.discord:
            try:
                self.discord.send_error_alert(
                    f"⚠️ 크론잡 오류: [{job_id}] {event.exception}"
                )
            except Exception:
                pass

    def _update_stats(self, job_id: str) -> None:
        """작업 통계를 업데이트합니다."""
        if job_id not in self.stats:
            self.stats[job_id] = {"runs": 0, "errors": 0, "last_run": None}
