# scripts/analyze_performance.py
"""
성과 분석 스크립트

데이터베이스에 기록된 거래 내역을 분석하여 통계를 출력합니다.

실행:
    python scripts/analyze_performance.py --days 30
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from loguru import logger
from src.database.models import get_connection
from src.utils.helpers import format_krw, format_pct


def get_trades_dataframe(days: int = 30) -> pd.DataFrame:
    """거래 데이터를 DataFrame으로 가져오기"""
    conn = get_connection()
    
    query = f"""
    SELECT * FROM trades
    WHERE exit_time IS NOT NULL
      AND datetime(exit_time) >= datetime('now', '-{days} days')
    ORDER BY exit_time DESC
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if not df.empty:
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        df["entry_time"] = pd.to_datetime(df["entry_time"])
    
    return df


def analyze_performance(days: int):
    """성과 분석"""
    logger.info(f"\n{'='*70}")
    logger.info(f"📊 성과 분석 (최근 {days}일)")
    logger.info(f"{'='*70}\n")
    
    df = get_trades_dataframe(days)
    
    if df.empty:
        logger.warning("⚠️  분석할 거래 기록이 없습니다.\n")
        return
    
    # 기본 통계
    total_trades = len(df)
    wins = len(df[df["pnl_krw"] > 0])
    losses = total_trades - wins
    win_rate = wins / total_trades if total_trades > 0 else 0
    
    total_pnl = df["pnl_krw"].sum()
    avg_pnl = df["pnl_krw"].mean()
    
    avg_win = df[df["pnl_krw"] > 0]["pnl_krw"].mean() if wins > 0 else 0
    avg_loss = df[df["pnl_krw"] < 0]["pnl_krw"].mean() if losses > 0 else 0
    
    best_trade = df.loc[df["pnl_krw"].idxmax()]
    worst_trade = df.loc[df["pnl_krw"].idxmin()]
    
    # 수익 팩터
    total_profit = df[df[df["pnl_krw"] > 0]["pnl_krw"].sum()]
    total_loss = abs(df[df["pnl_krw"] < 0]["pnl_krw"].sum())
    profit_factor = total_profit / total_loss if total_loss > 0 else 0
    
    # 페어별 통계
    pair_stats = df.groupby("pair").agg({
        "pnl_krw": ["count", "sum", "mean"],
    }).round(2)
    
    # 청산 사유별 통계
    exit_reason_stats = df.groupby("exit_reason").agg({
        "pnl_krw": ["count", "sum", "mean"],
    }).round(2)
    
    # 일별 손익
    df["date"] = df["exit_time"].dt.date
    daily_pnl = df.groupby("date")["pnl_krw"].sum()
    
    profitable_days = len(daily_pnl[daily_pnl > 0])
    total_days = len(daily_pnl)
    daily_win_rate = profitable_days / total_days if total_days > 0 else 0
    
    # 결과 출력
    print("📈 전체 통계")
    print("-"*70)
    print(f"총 거래 횟수:      {total_trades}회")
    print(f"승/패:             {wins}승 {losses}패")
    print(f"승률:              {format_pct(win_rate * 100)}")
    print(f"총 손익:           {format_krw(total_pnl)}")
    print(f"평균 손익:         {format_krw(avg_pnl)}")
    print(f"평균 수익:         {format_krw(avg_win)}")
    print(f"평균 손실:         {format_krw(avg_loss)}")
    print(f"수익 팩터:         {profit_factor:.2f}")
    print(f"최고 수익 거래:    {format_krw(best_trade['pnl_krw'])} ({best_trade['pair']})")
    print(f"최악 손실 거래:    {format_krw(worst_trade['pnl_krw'])} ({worst_trade['pair']})")
    
    print(f"\n📅 일별 통계 (총 {total_days}일)")
    print("-"*70)
    print(f"수익 일수:         {profitable_days}일")
    print(f"일별 승률:         {format_pct(daily_win_rate * 100)}")
    print(f"일평균 손익:       {format_krw(daily_pnl.mean())}")
    print(f"최고 수익 일:      {format_krw(daily_pnl.max())}")
    print(f"최악 손실 일:      {format_krw(daily_pnl.min())}")
    
    print("\n💹 페어별 성과")
    print("-"*70)
    print(pair_stats.to_string())
    
    print("\n📋 청산 사유별 통계")
    print("-"*70)
    print(exit_reason_stats.to_string())
    
    print("\n📆 최근 10일 일별 손익")
    print("-"*70)
    for date, pnl in daily_pnl.tail(10).items():
        emoji = "🟢" if pnl > 0 else "🔴"
        print(f"{emoji} {date} | {format_krw(pnl):>15}")
    
    print("\n" + "="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="거래 성과 분석")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="분석 기간 (일, 기본값: 30)"
    )
    
    args = parser.parse_args()
    
    logger.remove()
    logger.add(sys.stdout, format="<level>{message}</level>", level="INFO")
    
    analyze_performance(args.days)


if __name__ == "__main__":
    main()
