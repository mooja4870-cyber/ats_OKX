"""
백테스팅 엔진 — 과거 데이터 기반 전략 검증
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyupbit
from loguru import logger

from src.core.indicators import TechnicalIndicators
from src.core.signal_engine import SignalEngine
from src.utils.helpers import format_krw, format_pct


class BacktestResult:
    """백테스트 결과 데이터"""

    def __init__(self):
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = []
        self.initial_balance: float = 0.0
        self.final_balance: float = 0.0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.get("pnl_pct", 0) > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.get("pnl_pct", 0) <= 0)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def total_pnl_krw(self) -> float:
        return sum(t.get("pnl_krw", 0) for t in self.trades)

    @property
    def total_return_pct(self) -> float:
        if self.initial_balance > 0:
            return (self.final_balance - self.initial_balance) / self.initial_balance
        return 0.0

    @property
    def avg_win(self) -> float:
        wins = [t["pnl_pct"] for t in self.trades if t.get("pnl_pct", 0) > 0]
        return np.mean(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t["pnl_pct"] for t in self.trades if t.get("pnl_pct", 0) <= 0]
        return np.mean(losses) if losses else 0.0

    @property
    def reward_risk_ratio(self) -> float:
        if self.avg_loss != 0:
            return abs(self.avg_win / self.avg_loss)
        return float("inf") if self.avg_win > 0 else 0.0

    @property
    def max_drawdown(self) -> float:
        """최대 낙폭 (%)"""
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for val in self.equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        """샤프 비율 (연환산, 무위험=0 가정)"""
        if len(self.equity_curve) < 2:
            return 0.0
        returns = pd.Series(self.equity_curve).pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        # 1일 = 288개 5분봉, 연간 = 365일
        annualization = np.sqrt(288 * 365)
        return (returns.mean() / returns.std()) * annualization

    @property
    def profit_factor(self) -> float:
        """수익 팩터"""
        gross_profit = sum(t["pnl_krw"] for t in self.trades if t.get("pnl_krw", 0) > 0)
        gross_loss = abs(sum(t["pnl_krw"] for t in self.trades if t.get("pnl_krw", 0) < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def summary(self) -> Dict:
        """결과 요약"""
        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.final_balance,
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "avg_win_pct": self.avg_win,
            "avg_loss_pct": self.avg_loss,
            "reward_risk_ratio": self.reward_risk_ratio,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "total_pnl_krw": self.total_pnl_krw,
        }

    def print_summary(self) -> None:
        """결과 출력"""
        s = self.summary()
        print("\n" + "═" * 50)
        print("  📊 백테스트 결과")
        print("═" * 50)
        print(f"  시작 잔고:     {format_krw(s['initial_balance'])} KRW")
        print(f"  최종 잔고:     {format_krw(s['final_balance'])} KRW")
        print(f"  총 수익률:     {format_pct(s['total_return_pct'])}")
        print(f"  총 거래:       {s['total_trades']}회")
        print(f"  승/패:         {s['wins']}/{s['losses']}")
        print(f"  승률:          {s['win_rate']*100:.1f}%")
        print(f"  평균 수익:     {format_pct(s['avg_win_pct'])}")
        print(f"  평균 손실:     {format_pct(s['avg_loss_pct'])}")
        print(f"  R:R 비율:      {s['reward_risk_ratio']:.2f}")
        print(f"  수익 팩터:     {s['profit_factor']:.2f}")
        print(f"  최대 낙폭:     {format_pct(-s['max_drawdown_pct'])}")
        print(f"  샤프 비율:     {s['sharpe_ratio']:.2f}")
        print("═" * 50 + "\n")


class Backtester:
    """
    백테스팅 엔진

    과거 데이터에 동일 signal_engine 로직을 적용하여
    수수료 포함 시뮬레이션 수행.
    """

    def __init__(self, config: Dict):
        """
        Args:
            config: settings.yaml 전체 설정 딕셔너리
        """
        self.config = config
        ind_cfg = config.get("indicators", {})
        risk_cfg = config.get("risk", {})

        self.indicators = TechnicalIndicators(
            ema_fast=ind_cfg.get("ema_fast", 9),
            ema_slow=ind_cfg.get("ema_slow", 21),
            rsi_period=ind_cfg.get("rsi_period", 14),
            bb_period=ind_cfg.get("bb_period", 20),
            bb_std=ind_cfg.get("bb_std", 2.0),
            volume_avg_period=ind_cfg.get("volume_avg_period", 20),
        )
        self.signal_engine = SignalEngine(config)

        self.fee_rate = risk_cfg.get("fee_rate", 0.0005)
        self.risk_per_trade = risk_cfg.get("risk_per_trade_pct", 0.004)
        self.stop_loss_pct = risk_cfg.get("stop_loss_pct", 0.008)

        logger.info("Backtester 초기화")

    def fetch_data(
        self, pair: str, interval: str = "minute5", count: int = 200
    ) -> Optional[pd.DataFrame]:
        """과거 데이터 수집"""
        try:
            df = pyupbit.get_ohlcv(pair, interval=interval, count=count)
            if df is not None and not df.empty:
                logger.info(f"데이터 수집: {pair} {interval} {len(df)}개")
                return df
            return None
        except Exception as e:
            logger.error(f"데이터 수집 실패: {pair} — {e}")
            return None

    def run(
        self,
        pair: str,
        df_5m: pd.DataFrame,
        df_1h: pd.DataFrame,
        initial_balance: float = 1_000_000,
    ) -> BacktestResult:
        """
        백테스트 실행

        Args:
            pair: 거래 페어
            df_5m: 5분봉 데이터
            df_1h: 1시간봉 데이터
            initial_balance: 시작 잔고

        Returns:
            BacktestResult
        """
        result = BacktestResult()
        result.initial_balance = initial_balance
        balance = initial_balance
        position = None

        # 지표 계산
        df_5m = self.indicators.calculate_all(df_5m)
        df_1h = self.indicators.calculate_all(df_1h)

        logger.info(f"백테스트 시작: {pair}, 데이터={len(df_5m)}봉, 잔고={format_krw(balance)}")

        for i in range(50, len(df_5m)):
            current = df_5m.iloc[:i + 1]
            last = current.iloc[-1]
            current_price = last["close"]

            # 1시간봉 매칭 (가장 가까운 시간대)
            current_time = current.index[-1] if hasattr(current.index[-1], 'hour') else None
            # 간이: 1시간봉 전체 사용
            df_1h_window = df_1h

            if position:
                # 청산 체크
                sell_signal, exit_reason = self.signal_engine.check_sell_signal(
                    current, position
                )
                if sell_signal:
                    # 매도 실행
                    exit_price = current_price * (1 - self.fee_rate)  # 슬리피지 + 수수료
                    entry_price = position["entry_price"]
                    quantity = position["quantity"]

                    gross_pnl = (exit_price - entry_price) * quantity
                    buy_fee = entry_price * quantity * self.fee_rate
                    sell_fee = exit_price * quantity * self.fee_rate
                    net_pnl = gross_pnl - buy_fee - sell_fee
                    pnl_pct = net_pnl / (entry_price * quantity)

                    balance += (exit_price * quantity) - sell_fee

                    trade_record = {
                        "pair": pair,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "quantity": quantity,
                        "pnl_pct": pnl_pct,
                        "pnl_krw": net_pnl,
                        "exit_reason": exit_reason,
                        "entry_idx": position["entry_idx"],
                        "exit_idx": i,
                    }
                    result.trades.append(trade_record)
                    position = None

            else:
                # 매수 신호 체크
                buy_signal, score, conditions = self.signal_engine.check_buy_signal(
                    current, df_1h_window, pair
                )

                if buy_signal and score >= self.signal_engine.min_score:
                    # 매수 실행
                    entry_price = current_price * (1 + self.fee_rate)  # 슬리피지
                    target_price, stop_price = self.signal_engine.calc_targets(
                        entry_price, pair
                    )

                    # 포지션 크기
                    risk_amount = balance * self.risk_per_trade
                    price_diff = abs(entry_price - stop_price)
                    if price_diff > 0:
                        quantity = risk_amount / price_diff
                        invest_amount = quantity * entry_price
                        buy_fee = invest_amount * self.fee_rate

                        if invest_amount + buy_fee <= balance:
                            balance -= (invest_amount + buy_fee)
                            position = {
                                "pair": pair,
                                "entry_price": entry_price,
                                "quantity": quantity,
                                "target_price": target_price,
                                "stop_price": stop_price,
                                "entry_time": str(current.index[-1]),
                                "entry_idx": i,
                                "signal_score": score,
                            }

            result.equity_curve.append(
                balance + (position["quantity"] * current_price if position else 0)
            )

        # 미청산 포지션 정리
        if position:
            last_price = df_5m.iloc[-1]["close"]
            quantity = position["quantity"]
            balance += last_price * quantity * (1 - self.fee_rate)
            position = None

        result.final_balance = balance
        result.print_summary()
        return result

    def run_multi_pair(
        self,
        pairs: List[str],
        initial_balance: float = 1_000_000,
        candle_count: int = 200,
    ) -> Dict[str, BacktestResult]:
        """여러 페어 백테스트"""
        results = {}
        for pair in pairs:
            logger.info(f"═══ 백테스트: {pair} ═══")
            df_5m = self.fetch_data(pair, "minute5", candle_count)
            df_1h = self.fetch_data(pair, "minute60", candle_count // 12)

            if df_5m is not None and df_1h is not None:
                results[pair] = self.run(pair, df_5m, df_1h, initial_balance)
            else:
                logger.warning(f"데이터 불충분: {pair} — 스킵")

        return results
