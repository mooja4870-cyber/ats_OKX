"""리스크 관리 모듈 (OKX)"""
from __future__ import annotations

from loguru import logger
from src.utils.helpers import now_kst
from src.utils.constants import OKX_MIN_ORDER_USDT


class RiskManager:
    """포지션 사이징, 일일 손실 한도, 연속 손실 관리"""

    def __init__(self, config: dict, initial_balance: float):
        self.cfg = config["risk"]
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # 일일 카운터 (매일 리셋)
        self.daily_trades = 0
        self.daily_pnl_usdt = 0.0
        self.consecutive_losses = 0
        self.daily_date = now_kst().date()
        self.is_stopped = False
        self.stop_reason = ""

        # 설정값
        self.risk_per_trade = self.cfg["risk_per_trade_pct"]
        self.fixed_order_amount_usdt = float(
            self.cfg.get("fixed_order_amount_usdt", 0)
        )
        self.max_daily_loss = self.cfg["max_daily_loss_pct"]
        self.max_consec_losses = self.cfg["max_consecutive_losses"]
        self.fee_rate = self.cfg["fee_rate"]

        # 레버리지
        self.leverage = int(config["trading"].get("leverage", 1))

    def _check_daily_reset(self):
        """날짜 변경 시 일일 카운터 리셋"""
        today = now_kst().date()
        if today != self.daily_date:
            logger.info(f"[RiskMgr] 📅 일일 리셋: {self.daily_date} → {today}")
            self.daily_trades = 0
            self.daily_pnl_usdt = 0.0
            self.consecutive_losses = 0
            self.daily_date = today
            self.is_stopped = False
            self.stop_reason = ""

    def can_trade(self) -> bool:
        """매매 가능 여부 확인"""
        self._check_daily_reset()

        if self.is_stopped:
            logger.debug(f"[RiskMgr] 매매 중단 상태: {self.stop_reason}")
            return False

        # 하루 최대 손실
        max_loss_usdt = self.current_balance * self.max_daily_loss
        if self.daily_pnl_usdt <= -max_loss_usdt:
            self._stop(
                f"일일 최대 손실 도달 ({self.daily_pnl_usdt:,.2f} USDT)"
            )
            return False

        # 연속 패배
        if self.consecutive_losses >= self.max_consec_losses:
            self._stop(
                f"연속 {self.consecutive_losses}회 손실 — 당일 매매 종료"
            )
            return False

        return True

    def calculate_position_size(
        self,
        pair: str,
        entry_price: float,
        stop_loss_price: float,
        total_equity: float,
        available_balance: float,
        total_used_margin: float,
        current_atr_pct: float | None = None,
    ) -> dict | None:
        """
        포지션 크기 계산 (개선됨)

        Safety Checks:
          1. 총 사용 마진이 총자산의 20% 초과 시 금지
          2. 가용 잔고가 총자산의 50% 미만 시 금지
        
        Sizing Logic:
          - 기본 마진: 총자산의 3%
          - 동적 사이징: base_pct * (target_atr / current_atr)
          - 숏 포지션 동일 적용
        """
        # 0. 안전장치 체크
        max_margin_pct = self.cfg.get("max_total_margin_pct", 0.20)
        min_avail_pct = self.cfg.get("min_available_balance_pct", 0.50)

        if total_used_margin > total_equity * max_margin_pct:
            logger.warning(
                f"[RiskMgr] 진입 제한: 사용 마진 합계({total_used_margin:,.2f}) > "
                f"총자산의 {max_margin_pct*100}%"
            )
            return None
        
        if available_balance < total_equity * min_avail_pct:
            logger.warning(
                f"[RiskMgr] 진입 제한: 가용 잔고({available_balance:,.2f}) < "
                f"총자산의 {min_avail_pct*100}%"
            )
            return None

        # 1. 마진 비율 결정
        base_pct = self.cfg.get("margin_per_ticker_pct", 0.03)
        target_atr = self.cfg.get("target_atr_pct", 0.003)
        max_per_ticker_pct = self.cfg.get("max_per_ticker_pct", 0.04)

        margin_pct = base_pct
        if current_atr_pct and current_atr_pct > 0:
            margin_pct = base_pct * (target_atr / current_atr_pct)
            # 변동성 기반 캡 적용
            if margin_pct > max_per_ticker_pct:
                margin_pct = max_per_ticker_pct
        
        # 2. 금액 계산
        margin_usdt = total_equity * margin_pct
        notional_usdt = margin_usdt * self.leverage
        
        # 최소 주문금액 체크
        if notional_usdt < OKX_MIN_ORDER_USDT:
            logger.warning(
                f"[RiskMgr] {pair} 주문금액 {notional_usdt:.2f} < 최소 {OKX_MIN_ORDER_USDT}"
            )
            return None

        quantity = notional_usdt / entry_price
        price_risk = abs(entry_price - stop_loss_price) / entry_price
        risk_amount = notional_usdt * price_risk

        # 3. 상세 로그 기록
        logger.info(
            f"[RiskMgr] 📥 포지션 사이징: {pair}\n"
            f"   - 총자산: {total_equity:,.2f} USDT | 가용잔고: {available_balance:,.2f} USDT\n"
            f"   - 투입마진: {margin_usdt:,.2f} USDT ({margin_pct*100:.2f}%) | 레버리지: {self.leverage}x\n"
            f"   - 노셔널: {notional_usdt:,.2f} USDT | 사용마진합계: {total_used_margin:,.2f} USDT"
        )

        return {
            "order_amount_usdt": notional_usdt,
            "quantity": quantity,
            "margin_usdt": margin_usdt,
            "risk_amount_usdt": risk_amount,
            "margin_pct": margin_pct,
        }

    def update_balance(self, new_balance: float) -> None:
        """
        외부에서 실제 잔고(현금)를 동기화할 때 호출.
        매수/매도 후 실제 현금 잔고를 반영한다.
        """
        old = self.current_balance
        self.current_balance = new_balance
        if abs(old - new_balance) > 0.01:
            logger.debug(
                f"[RiskMgr] 잔고 동기화: {old:,.2f} → {new_balance:,.2f} USDT"
            )

    def record_trade_result(self, pnl_usdt: float, is_win: bool):
        """거래 결과 기록"""
        self.daily_trades += 1
        self.daily_pnl_usdt += pnl_usdt

        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        self.current_balance += pnl_usdt

        logger.info(
            f"[RiskMgr] 거래 #{self.daily_trades} 기록 | "
            f"PnL: {pnl_usdt:+,.2f} USDT | "
            f"일일 PnL: {self.daily_pnl_usdt:+,.2f} USDT | "
            f"연속 손실: {self.consecutive_losses}"
        )

    def calculate_fees(self, amount_usdt: float) -> float:
        """수수료 계산 (편도)"""
        return amount_usdt * self.fee_rate

    def _stop(self, reason: str):
        """매매 중단"""
        self.is_stopped = True
        self.stop_reason = reason
        logger.warning(f"[RiskMgr] 🛑 매매 중단: {reason}")

    def emergency_stop(self, reason: str = "수동 긴급 중지"):
        """긴급 중지"""
        self._stop(f"⚠️ EMERGENCY: {reason}")

    def get_status(self) -> dict:
        """현재 리스크 상태 요약"""
        return {
            "can_trade": self.can_trade() if not self.is_stopped else False,
            "daily_trades": self.daily_trades,
            "daily_pnl_usdt": self.daily_pnl_usdt,
            "consecutive_losses": self.consecutive_losses,
            "is_stopped": self.is_stopped,
            "stop_reason": self.stop_reason,
            "current_balance": self.current_balance,
        }
