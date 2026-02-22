# scripts/backtest_run.py
"""
백테스팅 실행 스크립트

과거 데이터를 사용하여 전략 성과를 시뮬레이션합니다.

실행:
    python scripts/backtest_run.py --pair KRW-BTC --start 2025-01-01 --end 2025-02-01
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pyupbit
from loguru import logger
from src.core.indicators import Indicators
from src.core.signal_engine import SignalEngine
from src.utils.helpers import load_config, format_krw, format_pct


class Backtester:
    """백테스팅 엔진"""

    def __init__(self, pair: str, start_date: str, end_date: str):
        self.pair = pair
        self.start_date = start_date
        self.end_date = end_date
        self.config = load_config()
        self.indicators = Indicators(self.config)
        self.signal_engine = SignalEngine(self.config)
        
        # 초기 설정
        self.initial_balance = 10_000_000  # 1천만원
        self.balance = self.initial_balance
        self.position = None
        self.trades = []
        self.fee_rate = self.config["risk"]["fee_rate"]

    def fetch_historical_data(self) -> pd.DataFrame:
        """과거 데이터 수집"""
        logger.info(f"📥 데이터 수집 중: {self.pair} ({self.start_date} ~ {self.end_date})")
        
        # 업비트는 한 번에 최대 200개 캔들만 제공하므로 여러 번 요청
        all_data = []
        current_end = self.end_date
        
        while True:
            df = pyupbit.get_ohlcv(self.pair, interval="minute5", to=current_end, count=200)
            if df is None or df.empty:
                break
            
            all_data.append(df)
            
            # 시작일보다 이전이면 중단
            if df.index[0].strftime("%Y-%m-%d") <= self.start_date:
                break
            
            # 다음 요청의 종료시점은 현재 데이터의 첫 시점
            current_end = df.index[0].strftime("%Y-%m-%d %H:%M:%S")
            
            # API Rate Limit 준수
            import time
            time.sleep(0.15)
        
        if not all_data:
            logger.error("❌ 데이터 수집 실패")
            return None
        
        # 데이터 병합 및 정렬
        df = pd.concat(all_data).sort_index()
        df = df[~df.index.duplicated(keep='first')]
        
        # 날짜 필터링
        df = df[(df.index >= self.start_date) & (df.index <= self.end_date)]
        
        # 컬럼명 표준화
        df.columns = ["open", "high", "low", "close", "volume"]
        
        logger.info(f"✅ {len(df)}개 캔들 수집 완료")
        return df

    def run(self):
        """백테스트 실행"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🔬 백테스트 시작: {self.pair}")
        logger.info(f"{'='*60}\n")
        
        # 데이터 수집
        df = self.fetch_historical_data()
        if df is None or len(df) < 100:
            logger.error("❌ 데이터 부족 (최소 100개 캔들 필요)")
            return
        
        # 지표 계산
        logger.info("📊 기술적 지표 계산 중...")
        df = self.indicators.calculate_all(df)
        
        # 백테스트 루프
        logger.info("⚙️  시뮬레이션 실행 중...\n")
        
        for i in range(50, len(df)):  # 지표 계산 안정화를 위해 50번째부터 시작
            current_data = df.iloc[:i+1]
            current_price = current_data.iloc[-1]["close"]
            current_time = current_data.index[-1]
            
            if self.position is None:
                # 매수 신호 체크
                signal = self.signal_engine.check_buy_signal(
                    self.pair, current_data, current_data
                )
                
                if signal.signal_type == "buy" and signal.score >= 70:
                    self._execute_buy(current_price, current_time, signal)
            else:
                # 매도 신호 체크
                signal = self.signal_engine.check_sell_signal(
                    self.pair, current_data, self.position
                )
                
                if signal.signal_type == "sell":
                    self._execute_sell(current_price, current_time, signal.reason)
        
        # 마지막 포지션 청산
        if self.position:
            final_price = df.iloc[-1]["close"]
            self._execute_sell(final_price, df.index[-1], "backtest_end")
        
        # 결과 출력
        self.print_results()

    def _execute_buy(self, price: float, time, signal):
        """매수 실행"""
        # 리스크 기반 포지션 사이징 (계좌의 0.4%)
        risk_amount = self.balance * 0.004
        stop_loss_pct = self.config["risk"]["stop_loss_pct"]
        
        order_amount = risk_amount / stop_loss_pct
        
        # 수수료 차감
        fee = order_amount * self.fee_rate
        actual_amount = order_amount - fee
        quantity = actual_amount / price
        
        self.position = {
            "entry_price": price,
            "entry_time": time,
            "quantity": quantity,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "signal_score": signal.score,
        }
        
        self.balance -= order_amount
        
        logger.debug(
            f"🟢 매수 | {time.strftime('%m-%d %H:%M')} | "
            f"가격: {price:,.0f} | 수량: {quantity:.8f} | "
            f"점수: {signal.score:.0f}"
        )

    def _execute_sell(self, price: float, time, reason: str):
        """매도 실행"""
        entry_price = self.position["entry_price"]
        quantity = self.position["quantity"]
        
        # 매도 금액
        sell_amount = quantity * price
        fee = sell_amount * self.fee_rate
        actual_amount = sell_amount - fee
        
        # 손익 계산
        buy_amount = quantity * entry_price
        pnl_krw = actual_amount - buy_amount
        pnl_pct = (price - entry_price) / entry_price
        
        # 보유 시간
        hold_time = time - self.position["entry_time"]
        hold_minutes = hold_time.total_seconds() / 60
        
        # 잔고 업데이트
        self.balance += actual_amount
        
        # 거래 기록
        self.trades.append({
            "entry_time": self.position["entry_time"],
            "exit_time": time,
            "entry_price": entry_price,
            "exit_price": price,
            "quantity": quantity,
            "pnl_pct": pnl_pct,
            "pnl_krw": pnl_krw,
            "hold_minutes": hold_minutes,
            "reason": reason,
            "signal_score": self.position["signal_score"],
        })
        
        emoji = "🔵" if pnl_krw > 0 else "🔴"
        logger.debug(
            f"{emoji} 매도 | {time.strftime('%m-%d %H:%M')} | "
            f"가격: {price:,.0f} | 손익: {pnl_pct:+.2%} ({format_krw(pnl_krw)}) | "
            f"사유: {reason}"
        )
        
        self.position = None

    def print_results(self):
        """결과 출력"""
        if not self.trades:
            logger.warning("\n⚠️  거래 기록이 없습니다.\n")
            return
        
        trades_df = pd.DataFrame(self.trades)
        
        # 통계 계산
        total_trades = len(trades_df)
        wins = len(trades_df[trades_df["pnl_krw"] > 0])
        losses = total_trades - wins
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        total_pnl = trades_df["pnl_krw"].sum()
        avg_win = trades_df[trades_df["pnl_krw"] > 0]["pnl_krw"].mean() if wins > 0 else 0
        avg_loss = trades_df[trades_df["pnl_krw"] < 0]["pnl_krw"].mean() if losses > 0 else 0
        profit_factor = abs(avg_win * wins / (avg_loss * losses)) if losses > 0 and avg_loss != 0 else 0
        
        avg_hold_time = trades_df["hold_minutes"].mean()
        
        # 최대 낙폭 계산
        cumulative_pnl = trades_df["pnl_krw"].cumsum()
        running_max = cumulative_pnl.cummax()
        drawdown = (cumulative_pnl - running_max) / self.initial_balance
        max_drawdown = drawdown.min()
        
        final_balance = self.balance
        total_return = (final_balance - self.initial_balance) / self.initial_balance
        
        # 결과 출력
        print("\n" + "="*60)
        print(f"{'🎯 백테스트 결과':^60}")
        print("="*60)
        print(f"페어: {self.pair}")
        print(f"기간: {self.start_date} ~ {self.end_date}")
        print("-"*60)
        print(f"초기 잔고:       {format_krw(self.initial_balance)}")
        print(f"최종 잔고:       {format_krw(final_balance)}")
        print(f"총 손익:         {format_krw(total_pnl)} ({format_pct(total_return * 100)})")
        print("-"*60)
        print(f"총 거래 횟수:    {total_trades}회")
        print(f"승/패:           {wins}승 {losses}패")
        print(f"승률:            {format_pct(win_rate * 100)}")
        print(f"평균 수익:       {format_krw(avg_win)}")
        print(f"평균 손실:       {format_krw(avg_loss)}")
        print(f"수익 팩터:       {profit_factor:.2f}")
        print(f"평균 보유시간:   {avg_hold_time:.0f}분")
        print(f"최대 낙폭:       {format_pct(max_drawdown * 100)}")
        print("="*60)
        
        # 상세 거래 내역 (최근 10건)
        print(f"\n{'📋 최근 거래 내역 (최근 10건)':^60}")
        print("-"*60)
        for idx, trade in trades_df.tail(10).iterrows():
            emoji = "🟢" if trade["pnl_krw"] > 0 else "🔴"
            print(
                f"{emoji} {trade['exit_time'].strftime('%m-%d %H:%M')} | "
                f"{trade['pnl_pct']:+6.2%} | {format_krw(trade['pnl_krw']):>12} | "
                f"{trade['reason']}"
            )
        print()


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="업비트 자동매매 백테스팅")
    parser.add_argument(
        "--pair",
        type=str,
        default="KRW-BTC",
        help="거래 페어 (기본값: KRW-BTC)"
    )
    parser.add_argument(
        "--start",
        type=str,
        default=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        help="시작 날짜 (YYYY-MM-DD, 기본값: 30일 전)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="종료 날짜 (YYYY-MM-DD, 기본값: 오늘)"
    )
    
    args = parser.parse_args()
    
    # 로깅 설정
    logger.remove()
    logger.add(
        sys.stdout,
        format="<level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )
    
    # 백테스트 실행
    backtester = Backtester(args.pair, args.start, args.end)
    backtester.run()


if __name__ == "__main__":
    main()
