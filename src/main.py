"""
메인 컨트롤러 — 초기화, 메인 루프, 스케줄러, 셧다운 (OKX 선물+현물)
"""

from __future__ import annotations

import asyncio
import signal
import sys
import ccxt
import pandas as pd
from typing import Dict, Optional

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.data_fetcher import DataFetcher
from src.core.indicators import Indicators
from src.core.order_executor import OrderExecutor
from src.core.position_tracker import PositionTracker
from src.core.risk_manager import RiskManager
from src.core.signal_engine import SignalEngine
from src.database.models import init_database
from src.database.trade_logger import TradeLogger
from src.notifications.discord_notifier import DiscordNotifier
from src.utils.helpers import (
    create_okx_exchange,
    format_usdt,
    load_config,
    now_kst,
    symbol_to_base,
)
from src.utils.constants import OKX_MIN_ORDER_USDT


class MainController:
    """
    메인 컨트롤러 (OKX)

    - 초기화 시퀀스 (설정→API→디스코드→DB→리스크매니저)
    - asyncio 메인 루프 (10초 간격)
    - 롱/숏 양방향 매매
    - 스케줄 작업 (하트비트, 일일리포트)
    - 그레이스풀 셧다운
    """

    def __init__(self):
        self.running = False
        self._shutdown_requested = False
        self._shutdown_completed = False
        self.config: Dict = {}

        # 모듈 인스턴스
        self.exchange: Optional[ccxt.okx] = None
        self.data_fetcher: Optional[DataFetcher] = None
        self.indicators: Optional[Indicators] = None
        self.signal_engine: Optional[SignalEngine] = None
        self.order_executor: Optional[OrderExecutor] = None
        self.position_tracker: Optional[PositionTracker] = None
        self.risk_manager: Optional[RiskManager] = None
        self.notifier: Optional[DiscordNotifier] = None

        # 스케줄러
        self.scheduler = AsyncIOScheduler()

        # 스케줄 카운터
        self._loop_count = 0
        self._start_time = now_kst()

    # ═══════════════════════════════════════════
    #  초기화
    # ═══════════════════════════════════════════
    def initialize(self) -> bool:
        """
        초기화 시퀀스 실행

        Returns:
            True = 성공, False = 실패
        """
        logger.info("═══ OKX 선물+현물 자동매매 봇 초기화 ═══")

        # 1. 설정 파일 로드
        try:
            self.config = load_config()
            logger.info("✅ 설정 파일 로드 완료")
        except Exception as e:
            logger.critical(f"설정 파일 로드 실패: {e}")
            return False

        trading = self.config.get("trading", {})
        mode = trading.get("mode", "paper")

        # 2. OKX Exchange 생성
        try:
            self.exchange = create_okx_exchange(mode)
            if mode == "live":
                logger.info("✅ OKX LIVE 연결 완료")
            elif mode == "demo":
                logger.info("✅ OKX DEMO 연결 완료 (샌드박스)")
            else:
                logger.info("✅ OKX Public API 연결 (Paper 모드)")
        except Exception as e:
            logger.critical(f"OKX 연결 실패: {e}")
            return False

        # 3. 데이터베이스 초기화
        init_database()

        # 4. 데이터 수집기
        self.data_fetcher = DataFetcher(self.exchange)

        # 5. 기술적 지표
        self.indicators = Indicators(self.config)

        # 6. 신호 엔진
        self.signal_engine = SignalEngine(self.config)

        # 7. 주문 실행기
        try:
            self.order_executor = OrderExecutor(self.config, self.exchange)
            logger.info(f"✅ 주문 실행기 초기화 (모드: {mode})")
        except Exception as e:
            logger.critical(f"주문 실행기 초기화 실패: {e}")
            return False

        # 8. 포지션 추적기
        self.position_tracker = PositionTracker()

        # 시작 잔고 확인
        if mode == "paper":
            usdt_balance = self.order_executor.get_paper_balance().get("usdt", 0)
        else:
            balances = self.data_fetcher.get_balance(
                market_type=trading.get("market_type", "swap")
            )
            usdt_balance = balances.get("USDT", {}).get("total", 0)
            if not usdt_balance:
                logger.warning(
                    "실계좌 USDT 잔고 조회 실패 — 리스크 초기값 10,000 USDT 사용"
                )
                usdt_balance = 10_000

        # 9. 리스크 매니저
        self.risk_manager = RiskManager(self.config, usdt_balance)
        logger.info(f"💰 시작 잔고: {format_usdt(usdt_balance)}")

        # 10. 디스코드 알림
        try:
            self.notifier = DiscordNotifier(self.config)
            asyncio.create_task(self.notifier.notify_system(
                "봇 시작",
                f"거래소: OKX\n"
                f"매매 모드: {mode}\n"
                f"마켓: {trading.get('market_type', 'swap')}\n"
                f"레버리지: {trading.get('leverage', 1)}x\n"
                f"페어: {', '.join(trading.get('pairs', []))}\n"
                f"잔고: {format_usdt(usdt_balance)}",
            ))
            logger.info("✅ 디스코드 알림 연결 완료")
        except ValueError as e:
            logger.warning(f"⚠️ 디스코드 Webhook 생략: {e}")

        # 스케줄러 등록
        self.scheduler.add_job(
            self._daily_summary_task,
            "cron",
            hour=23,
            minute=55,
            timezone="Asia/Seoul",
        )
        self.scheduler.start()

        logger.info("═══ 초기화 완료 ═══")
        return True

    # ═══════════════════════════════════════════
    #  잔고 조회 헬퍼
    # ═══════════════════════════════════════════
    def _get_wallet_balance_usdt(self) -> float:
        """
        실제 지갑 잔고(Wallet Balance)를 조회한다.
        Paper 모드 → OrderExecutor의 가상 지갑 잔고
        Live/Demo 모드 → DataFetcher를 통한 거래소 지갑 잔고
        """
        mode = self.config.get("trading", {}).get("mode", "paper")
        if mode == "paper":
            return float(
                self.order_executor.get_paper_balance().get("usdt", 0.0)
            )
        else:
            market_type = self.config["trading"].get("market_type", "swap")
            balances = self.data_fetcher.get_balance(market_type=market_type)
            return float(balances.get("USDT", {}).get("total", 0.0))

    def _sync_risk_manager_balance(self) -> None:
        """
        RiskManager의 current_balance를 실제 지갑 잔고와 동기화한다.
        매수/매도 후 반드시 호출하여 잔고 불일치를 방지한다.
        """
        wallet_balance = self._get_wallet_balance_usdt()
        self.risk_manager.update_balance(wallet_balance)

    # ═══════════════════════════════════════════
    #  메인 루프
    # ═══════════════════════════════════════════
    async def main_loop(self) -> None:
        """메인 매매 루프"""
        from src.utils.helpers import is_trading_session

        trading = self.config.get("trading", {})
        pairs = trading.get("pairs", ["BTC/USDT:USDT"])
        interval = trading.get("loop_interval_seconds", 10)
        timeframe_main = trading.get("timeframe_main", "5m")
        timeframe_trend = trading.get("timeframe_trend", "1h")
        market_type = trading.get("market_type", "swap")

        self.running = True
        logger.info(f"메인 루프 시작 (간격: {interval}초, 페어: {pairs})")

        while self.running:
            try:
                self._loop_count += 1
                if self._loop_count % 6 == 0:  # 약 1분마다
                    logger.info(f"[Main] Loop Heartbeat #{self._loop_count} | Uptime: {self._loop_count * interval}s")

                # 매매 가능 여부 확인
                if not self.risk_manager.can_trade():
                    await self._scheduled_tasks()
                    await asyncio.sleep(interval)
                    continue

                # 세션 확인
                if not is_trading_session(self.config):
                    await self._scheduled_tasks()
                    await asyncio.sleep(interval)
                    continue

                for pair in pairs:
                    if not self.running:
                        break
                    await self._process_pair(
                        pair, timeframe_main, timeframe_trend, market_type
                    )

                # 0. 교차 검증 (Sync Check)
                await self._sync_with_exchange()

                # 스케줄 작업
                await self._scheduled_tasks()

            except Exception as e:
                logger.error(f"메인 루프 에러: {e}")
                if self.notifier:
                    await self.notifier.notify_error(f"메인 루프 에러: {e}")

            await asyncio.sleep(interval)

    async def _process_pair(
        self,
        pair: str,
        timeframe_main: str,
        timeframe_trend: str,
        market_type: str,
    ) -> None:
        """페어별 처리 (롱+숏)"""
        try:
            # 1. 데이터 수집
            df_5m = self.data_fetcher.get_candles(pair, timeframe_main)
            df_1h = self.data_fetcher.get_candles(pair, timeframe_trend)

            if df_5m is None or df_1h is None:
                return

            # 2. 지표 계산
            df_5m = self.indicators.calculate_all(df_5m)
            df_1h = self.indicators.calculate_all(df_1h)

            # 3. 포지션 체크
            position = self.position_tracker.get_position(pair)

            if position:
                # ── 고점/저점(peak_price) 업데이트 ──
                current_price = df_5m.iloc[-1]["close"]
                peak_price = position.get("peak_price", position["entry_price"])
                pos_side = position.get("position_side", "long")
                
                if pos_side == "long":
                    if current_price > peak_price:
                        self.position_tracker.update_position(pair, {"peak_price": current_price})
                else: 
                    if current_price < peak_price:
                        self.position_tracker.update_position(pair, {"peak_price": current_price})

                # 최신 상태로 다시 가져옴 (peak_price가 반영된 상태)
                position = self.position_tracker.get_position(pair)

                # 청산 조건 체크
                exit_signal = self.signal_engine.check_exit_signal(
                    pair, df_5m, position
                )

                TradeLogger.save_signal({
                    "timestamp": exit_signal.timestamp,
                    "pair": pair,
                    "signal_type": exit_signal.signal_type,
                    "score": exit_signal.score,
                    "conditions": exit_signal.conditions,
                    "acted": exit_signal.signal_type == "exit",
                    "reason_skipped": (
                        exit_signal.reason
                        if exit_signal.signal_type != "exit"
                        else ""
                    ),
                })

                if exit_signal.signal_type == "exit":
                    await self._execute_close(
                        pair, position, exit_signal.reason, df_5m, 
                        quantity_pct=getattr(exit_signal, "quantity_pct", 1.0)
                    )
            else:
                # ── 롱 신호 확인 ──
                long_signal = self.signal_engine.check_long_signal(
                    pair, df_5m, df_1h
                )

                TradeLogger.save_signal({
                    "timestamp": long_signal.timestamp,
                    "pair": pair,
                    "signal_type": long_signal.signal_type,
                    "score": long_signal.score,
                    "conditions": long_signal.conditions,
                    "acted": long_signal.signal_type == "long",
                    "reason_skipped": (
                        long_signal.reason
                        if long_signal.signal_type != "long"
                        else ""
                    ),
                })

                min_score = float(
                    self.config.get("trading", {}).get("buy_min_score", 70)
                )

                if (
                    long_signal.signal_type == "long"
                    and long_signal.score >= min_score
                ):
                    await self._execute_open(
                        pair, df_5m, long_signal, "long"
                    )
                elif market_type in ("swap", "both"):
                    # ── 숏 신호 확인 (선물 모드에서만) ──
                    short_signal = self.signal_engine.check_short_signal(
                        pair, df_5m, df_1h
                    )

                    TradeLogger.save_signal({
                        "timestamp": short_signal.timestamp,
                        "pair": pair,
                        "signal_type": short_signal.signal_type,
                        "score": short_signal.score,
                        "conditions": short_signal.conditions,
                        "acted": short_signal.signal_type == "short",
                        "reason_skipped": (
                            short_signal.reason
                            if short_signal.signal_type != "short"
                            else ""
                        ),
                    })

                    if (
                        short_signal.signal_type == "short"
                        and short_signal.score >= min_score
                    ):
                        await self._execute_open(
                            pair, df_5m, short_signal, "short"
                        )

        except Exception as e:
            logger.error(f"페어 처리 에러: {pair} — {e}")

    async def _execute_open(
        self,
        pair: str,
        df_5m: pd.DataFrame,
        entry_signal,
        position_side: str,
    ) -> None:
        """롱/숏 포지션 진입 (개선된 사이징 반영)"""
        current_price = df_5m.iloc[-1]["close"]
        current_atr_pct = df_5m.iloc[-1].get("atr_pct", 0.0)

        # 1. 현재 계계 상태 스냅샷 (Equity, Used Margin 등)
        snapshot = self._collect_balance_snapshot()
        total_equity = snapshot["total_value_usdt"]
        available_usdt = snapshot["cash_usdt"]
        total_used_margin = snapshot["total_used_margin"]

        # 2. 포지션 크기 결정 (RiskManager)
        amount_dict = self.risk_manager.calculate_position_size(
            pair=pair,
            entry_price=current_price,
            stop_loss_price=entry_signal.stop_loss,
            total_equity=total_equity,
            available_balance=available_usdt,
            total_used_margin=total_used_margin,
            current_atr_pct=current_atr_pct,
        )

        if not amount_dict:
            return

        amount_usdt = amount_dict["order_amount_usdt"]

        # 3. 실제 주문 가능 여부 재확인 (Slippage/Fee 고려하여 약간의 여유)
        if amount_usdt > available_usdt * 0.99:
            logger.warning(
                f"[Main] 주문금액 조정({pair}): "
                f"{format_usdt(amount_usdt)} -> {format_usdt(available_usdt * 0.99)} (가용잔고 부족)"
            )
            amount_usdt = available_usdt * 0.99
            if amount_usdt < OKX_MIN_ORDER_USDT:
                return

        # 주문 실행
        if position_side == "long":
            trade_result = self.order_executor.open_long(pair, amount_usdt)
        else:
            trade_result = self.order_executor.open_short(pair, amount_usdt)

        if not trade_result:
            logger.error(f"포지션 진입 실패: {pair} ({position_side})")
            return

        # 포지션 등록
        self.position_tracker.open_position(
            pair=pair,
            entry_price=trade_result["price"],
            quantity=trade_result["quantity"],
            take_profit=entry_signal.take_profit,
            stop_loss=entry_signal.stop_loss,
            trade_id=trade_result["trade_id"],
            initial_margin=trade_result["initial_margin"],
            position_side=position_side,
            market_type=self.config["trading"].get("market_type", "swap"),
        )

        # 거래 기록
        TradeLogger.save_trade({
            "trade_id": trade_result["trade_id"],
            "pair": pair,
            "side": trade_result["side"],
            "entry_price": trade_result["price"],
            "quantity": trade_result["quantity"],
            "entry_time": trade_result["timestamp"],
            "fee_usdt": trade_result.get("fee_usdt", 0),
            "signal_score": entry_signal.score,
            "trade_mode": trade_result["mode"],
            "position_side": position_side,
        })

        # ★ 매수 후 RiskManager 잔고 동기화 (총자산 계산 오류 방지)
        self._sync_risk_manager_balance()

        # 디스코드 알림
        if self.notifier:
            await self.notifier.notify_buy(trade_result, entry_signal.__dict__)

    async def _execute_close(
        self, pair: str, position: dict, exit_reason: str, df_5m: pd.DataFrame, quantity_pct: float = 1.0
    ) -> None:
        """포지션 청산 (부분 청산 지원)"""
        current_price = df_5m.iloc[-1]["close"]
        full_quantity = position["quantity"]
        initial_qty = position.get("initial_quantity", full_quantity)
        
        # 실제 청산할 수량 결정
        if quantity_pct >= 1.0:
            qty_to_close = full_quantity
        else:
            # TP1, TP2 등 부분 청산 (initial 기준 지정 비율)
            qty_to_close = initial_qty * quantity_pct
            # 현재 보유량보다 많이 털 수는 없음
            if qty_to_close > full_quantity:
                qty_to_close = full_quantity

        entry_price = position["entry_price"]
        position_side = position.get("position_side", "long")

        # 주문 실행
        trade_result = self.order_executor.close_position(
            pair, qty_to_close, position_side
        )
        if not trade_result:
            logger.error(f"포지션 청산 실패: {pair} ({exit_reason})")
            return

        exit_price = trade_result["price"]

        # 손익 계산 (롱/숏 구분)
        if position_side == "long":
            gross_pnl_usdt = (exit_price - entry_price) * qty_to_close
        else:  # short
            gross_pnl_usdt = (entry_price - exit_price) * qty_to_close

        if self.config.get("trading", {}).get("mode", "paper") == "paper":
            self.order_executor.add_paper_pnl(gross_pnl_usdt)

        pnl_usdt = gross_pnl_usdt - trade_result.get("fee_usdt", 0)
        pnl_usdt -= self.risk_manager.calculate_fees(entry_price * qty_to_close)

        if position_side == "long":
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price

        from datetime import datetime
        entry_time = datetime.fromisoformat(position["entry_time"])
        hold_minutes = (now_kst() - entry_time).total_seconds() / 60

        # 포지션 상태 업데이트
        is_full_close = (qty_to_close >= full_quantity) or (quantity_pct >= 1.0)
        
        if is_full_close:
            # 전량 종료
            self.position_tracker.close_position(pair)
            self.risk_manager.record_trade_result(pnl_usdt, pnl_pct >= 0)
        else:
            # 부분 종료 (TP1, TP2)
            new_qty = full_quantity - qty_to_close
            updates = {"quantity": new_qty}
            
            # 단계 업데이트 (건너뛰기 고려)
            current_stage = position.get("tp_stage_hit", 0)
            if exit_reason == "TP1":
                updates["tp_stage_hit"] = max(current_stage, 1)
            elif exit_reason == "TP2":
                updates["tp_stage_hit"] = max(current_stage, 2)
            
            # TP 단계 진입 시 트레일링 스탑 활성화
            updates["trailing_active"] = True
            
            self.position_tracker.update_position(pair, updates)
            # 부분 익절도 실현 손익으로 기록
            self.risk_manager.record_trade_result(pnl_usdt, pnl_pct >= 0)

        self._sync_risk_manager_balance()

        # 거래 기록 저장
        TradeLogger.save_trade({
            "trade_id": position["trade_id"],
            "pair": pair,
            "side": trade_result["side"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": qty_to_close,
            "entry_time": position["entry_time"],
            "exit_time": trade_result["timestamp"],
            "pnl_pct": pnl_pct,
            "pnl_usdt": pnl_usdt,
            "fee_usdt": trade_result.get("fee_usdt", 0),
            "exit_reason": exit_reason,
            "trade_mode": trade_result["mode"],
            "position_side": position_side,
        })

        # 디스코드 알림
        if self.notifier:
            await self.notifier.notify_sell(
                trade_result,
                entry_price,
                exit_reason,
                pnl_pct,
                pnl_usdt,
                hold_minutes,
            )

    async def _sync_with_exchange(self) -> None:
        """
        봇 DB(PositionTracker)와 실제 거래소 포지션 교차 검증 (Strict Mode)
        """
        try:
            exchange_positions = self.order_executor.get_all_positions_standardized()
            db_positions = self.position_tracker.get_all_positions() # {pair: pos_dict}
            
            # 1. DB에는 있으나 거래소에는 없는 경우 (강제청산 또는 수동청산 의심)
            for pair in list(db_positions.keys()):
                db_pos = db_positions[pair]
                match = next((p for p in exchange_positions if p['pair'] == pair and p['side'] == db_pos['position_side']), None)
                
                if not match:
                    logger.warning(f"[Sync] 포지션 증량 감지 (Exchange에서 사라짐): {pair} ({db_pos['position_side']})")
                    if self.notifier:
                        await self.notifier.notify_sync_warning(
                            f"**⚠️ [포지션 증발 감지]**\n"
                            f"• 종목: {pair}\n"
                            f"• 방향: {db_pos['position_side'].upper()}\n"
                            f"• DB에는 존재하나 거래소에서 사라졌습니다. DB를 리셋합니다."
                        )
                    self.position_tracker.close_position(pair)

            # 2. 거래소에는 있으나 DB에는 없는 경우 (미관리 포지션 → 즉시 청산)
            for ex_pos in exchange_positions:
                pair = ex_pos['pair']
                side = ex_pos['side']
                qty = ex_pos['qty']
                
                db_pos = db_positions.get(pair)
                if not db_pos or db_pos['position_side'] != side:
                    logger.critical(f"[Sync] 미관리 포지션 감지 및 즉시 청산: {pair} ({side}) {qty}")
                    
                    # 즉시 시장가 청산
                    self.order_executor.close_position(pair, qty, side)
                    
                    if self.notifier:
                        msg = (
                            f"⚠️ **[미관리 포지션 감지 → 자동 청산]**\n"
                            f"• 티커: {pair}\n"
                            f"• 방향: {side.upper()}\n"
                            f"• 수량: {qty:.6f}\n"
                            f"• 사유: 봇 DB에 없는 포지션"
                        )
                        await self.notifier._send_webhook(self.notifier.webhook_error, {"description": msg, "color": self.notifier.colors["emergency"]})

        except Exception as e:
            logger.error(f"[Sync] 교차 검증 에러: {e}")

    # ═══════════════════════════════════════════
    #  스케줄 작업
    # ═══════════════════════════════════════════
    def _collect_balance_snapshot(self) -> dict:
        """현금/보유평가/총자산 스냅샷 수집 (봇 DB 기준)"""
        mode = self.config.get("trading", {}).get("mode", "paper")
        now_str = now_kst().strftime("%Y-%m-%d %H:%M:%S")
        holdings_items = []
        total_unrealized_pnl = 0.0
        holdings_value_usdt = 0.0

        # [지침 3.3] 모든 지표는 봇 DB 기준으로 계산
        if mode == "paper":
            paper_balance = self.order_executor.get_paper_balance()
            wallet_balance = float(paper_balance.get("usdt", 0.0))
        else:
            market_type = self.config["trading"].get("market_type", "swap")
            balances = self.data_fetcher.get_balance(market_type=market_type)
            wallet_balance = float(balances.get("USDT", {}).get("total", 0.0))

        # 봇 DB 관리 포지션만 순회
        managed_positions = self.position_tracker.get_all_positions()
        pairs = list(managed_positions.keys())
        prices = self.data_fetcher.get_current_prices(pairs) if pairs else {}

        for pair, pos in managed_positions.items():
            price = prices.get(pair, pos["entry_price"])
            pnl_info = self.position_tracker.get_unrealized_pnl(pair, price)
            
            if pnl_info:
                margin = pos.get("initial_margin", 0.0)
                eval_total = margin + pnl_info["pnl_usdt"]
                total_unrealized_pnl += pnl_info["pnl_usdt"]
                holdings_value_usdt += eval_total
                
                holdings_items.append({
                    "symbol": f"{'SHORT_' if pos.get('position_side') == 'short' else ''}{pair.split('/')[0]}",
                    "buy_total_usdt": margin,
                    "eval_total_usdt": eval_total,
                    "diff_usdt": pnl_info["pnl_usdt"],
                    "diff_pct": (pnl_info["pnl_usdt"] / margin * 100) if margin > 0 else 0.0,
                    "side": pos.get("position_side", "long")
                })

        # [지침 3.3] 총자산 = 현금 + 미실현손익 (봇 DB 기준)
        total_equity = wallet_balance + total_unrealized_pnl

        return {
            "time": now_str,
            "mode": mode,
            "cash_usdt": wallet_balance,
            "unrealized_pnl_usdt": total_unrealized_pnl,
            "total_value_usdt": total_equity,
            "holdings_items": holdings_items,
            "total_used_margin": sum(item["buy_total_usdt"] for item in holdings_items)
        }

    async def _scheduled_tasks(self) -> None:
        """주기적 스케줄 작업 — Discord.md 기준"""
        if not self.notifier:
            return

        conf = self.config.get("discord", {})
        interval = self.config.get("trading", {}).get("loop_interval_seconds", 10)
        
        # 1. 1분 주기: 포지션 모니터링
        interval_1m = int(conf.get("report_1m_interval_seconds", 60))
        if (self._loop_count * interval) % interval_1m < interval:
            await self._send_position_report_1m()

        # 2. 5분 주기: 시장 스냅샷
        interval_5m = int(conf.get("report_5m_interval_seconds", 300))
        if (self._loop_count * interval) % interval_5m < interval:
            await self._send_market_snapshot_5m()

        # 3. 15분 주기: 성과 리포트
        interval_15m = int(conf.get("report_15m_interval_seconds", 900))
        if (self._loop_count * interval) % interval_15m < interval:
            await self._send_performance_report_15m()

        # 4. 1시간 주기: 종합 리포트
        interval_1h = int(conf.get("report_1h_interval_seconds", 3600))
        if (self._loop_count * interval) % interval_1h < interval:
            logger.info(f"[Scheduled] 1시간 종합 리포트 전송 시작 (Loop #{self._loop_count})")
            await self._send_hourly_report_1h()

    async def _send_position_report_1m(self):
        """1분 잔고 스냅샷 리포트"""
        snapshot = self._collect_balance_snapshot()
        initial_capital = self.config.get("risk", {}).get("initial_capital", 10000.0)
        
        cash_usdt = snapshot["cash_usdt"]
        total_assets = snapshot["total_value_usdt"]
        total_pnl_pct = (total_assets / initial_capital) - 1 if initial_capital > 0 else 0.0

        stats = {
            "time": snapshot["time"],
            "total_assets": total_assets,
            "total_pnl_pct": total_pnl_pct,
            "cash_usdt": cash_usdt,
            "eval_total_usdt": snapshot.get("total_used_margin", 0.0) + snapshot.get("unrealized_pnl_usdt", 0.0),
            "unrealized_pnl_usdt": snapshot.get("unrealized_pnl_usdt", 0.0),
            "unrealized_pnl_pct": (snapshot.get("unrealized_pnl_usdt", 0.0) / snapshot.get("total_used_margin", 1.0) * 100) if snapshot.get("total_used_margin", 0) > 0 else 0.0,
            "holdings": [{"symbol": i["symbol"], "eval_usdt": i["eval_total_usdt"], "pnl_pct": i["diff_pct"]} for i in snapshot.get("holdings_items", [])],
        }
        await self.notifier.notify_position_report_1m(stats)

    async def _send_market_snapshot_5m(self):
        """5분 시장 스냅샷"""
        pairs = self.config["trading"].get("pairs", [])
        prices = self.data_fetcher.get_current_prices(pairs)
        markets = {p.split('/')[0]: {"price": prices.get(p, 0), "chg_5m": 0.0, "chg_1h": 0.0} for p in pairs}
        snapshot = {"time": now_kst().strftime("%Y-%m-%d %H:%M:%S"), "markets": markets, "signals": {}}
        await self.notifier.notify_market_snapshot_5m(snapshot)

    async def _send_performance_report_15m(self):
        """15분 성과 리포트"""
        rm = self.risk_manager
        snapshot = self._collect_balance_snapshot()
        total_assets = snapshot["total_value_usdt"]
        margin_ratio = (snapshot.get("total_used_margin", 0) / total_assets * 100) if total_assets > 0 else 0.0
        
        stats = {
            "time": snapshot["time"],
            "realized_pnl": rm.daily_pnl_usdt,
            "unrealized_pnl": snapshot.get("unrealized_pnl_usdt", 0.0),
            "trades": rm.daily_trades,
            "wins": max(0, rm.daily_trades - rm.consecutive_losses),
            "losses": rm.consecutive_losses,
            "win_rate": (rm.daily_trades - rm.consecutive_losses) / rm.daily_trades * 100 if rm.daily_trades > 0 else 0,
            "total_assets": total_assets,
            "free_balance": snapshot["cash_usdt"],
            "margin_ratio": margin_ratio,
            "max_dd": 0.0,
            "consec_losses": rm.consecutive_losses,
        }
        await self.notifier.notify_performance_report_15m(stats)

    async def _send_hourly_report_1h(self):
        """1시간 주기 종합 리포트 전송"""
        now = now_kst()
        one_hour_ago = now - timedelta(hours=1)
        
        start_str = one_hour_ago.strftime("%Y-%m-%d %H:%M:%S")
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        stats = TradeLogger.get_detailed_stats(start_str, end_str)
        snapshot = self._collect_balance_snapshot()
        
        # 시장 환경 데이터 (BTC 기준)
        btc_info = {"chg_24h": 0.0, "volume_ratio": 1.0}
        try:
            ticker = self.data_fetcher.get_ticker("BTC/USDT:USDT")
            if ticker:
                btc_info["chg_24h"] = ticker.get("percentage", 0.0)
        except: pass

        report_data = {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "stats": stats,
            "snapshot": snapshot,
            "market": btc_info
        }
        await self.notifier.notify_hourly_report_1h(report_data)

    async def _daily_summary_task(self):
        """매일 23:55에 당일 요약 생성"""
        today = now_kst().strftime("%Y-%m-%d")
        stats = TradeLogger.calculate_daily_stats(today)
        
        snapshot = self._collect_balance_snapshot()
        stats["balance_start"] = self.config.get("risk", {}).get("initial_capital", 10000.0)
        stats["balance_end"] = snapshot["total_value_usdt"]
        
        # 운영일수 계산
        uptime = now_kst() - self._start_time
        stats["day_num"] = uptime.days + 1

        TradeLogger.save_daily_summary(today, stats)

        if self.notifier:
            await self.notifier.notify_daily_report({"date": today, **stats})

        logger.info(f"[Bot] 📊 일일 요약 완료: {today}")

    # ═══════════════════════════════════════════
    #  그레이스풀 셧다운
    # ═══════════════════════════════════════════
    def _signal_handler(self, signum, frame) -> None:
        """SIGINT/SIGTERM 핸들러"""
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        sig_name = signal.Signals(signum).name
        logger.warning(f"시그널 수신: {sig_name} — 셧다운 시작")
        self.running = False

    async def shutdown(self) -> None:
        """그레이스풀 셧다운"""
        if self._shutdown_completed:
            return

        logger.info("═══ 봇 셧다운 시작 ═══")
        self.running = False

        open_positions = self.position_tracker.get_all_positions()
        if open_positions:
            logger.warning(
                f"미청산 포지션 {len(open_positions)}개 — 자동 청산 없음 "
                "(포지션/종이잔고 상태는 파일로 유지됨)"
            )

        today = now_kst().strftime("%Y-%m-%d")
        stats = TradeLogger.calculate_daily_stats(today)
        stats["balance_end"] = self.risk_manager.current_balance
        TradeLogger.save_daily_summary(today, stats)

        if self.notifier:
            status = self.risk_manager.get_status()
            await self.notifier.notify_shutdown(status)
            await self.notifier.close()

        self._shutdown_completed = True
        logger.info("═══ 봇 셧다운 완료 ═══")

    # ═══════════════════════════════════════════
    #  실행
    # ═══════════════════════════════════════════
    async def run(self) -> None:
        """봇 실행"""
        if not self.initialize():
            logger.critical("초기화 실패 — 종료")
            return

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            await self.main_loop()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt 수신")
        finally:
            await self.shutdown()


def main():
    """진입점"""
    controller = MainController()
    asyncio.run(controller.run())


if __name__ == "__main__":
    main()
