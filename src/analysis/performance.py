"""
성과 분석 및 시각화 모듈 — 수익 곡선, 매매 차트, 성과 지표
"""

from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # 비GUI 백엔드
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import mplfinance as mpf
import numpy as np
import pandas as pd
from loguru import logger

from src.utils.helpers import get_project_root


class PerformanceAnalyzer:
    """
    성과 분석 및 시각화 클래스

    - 누적 수익 곡선
    - 매매 지점 표시 캔들 차트
    - 일별/주별 성과
    - PNG 저장
    """

    def __init__(self, output_dir: str = "data/charts"):
        self.output_dir = get_project_root() / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"PerformanceAnalyzer 초기화 (output={self.output_dir})")

    # ───────────────────────────────────────
    #  누적 수익 곡선
    # ───────────────────────────────────────
    def plot_equity_curve(
        self,
        equity_curve: List[float],
        title: str = "누적 수익 곡선",
        filename: str = "equity_curve.png",
    ) -> str:
        """
        누적 수익 곡선 그래프 생성

        Returns:
            저장된 파일 경로
        """
        fig, ax = plt.subplots(figsize=(14, 6))

        ax.plot(equity_curve, color="#2196F3", linewidth=1.5, label="자산 가치")
        ax.fill_between(
            range(len(equity_curve)),
            equity_curve,
            equity_curve[0],
            alpha=0.1,
            color="#2196F3",
        )

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("봉 번호")
        ax.set_ylabel("자산 가치 (KRW)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        filepath = str(self.output_dir / filename)
        fig.tight_layout()
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"수익 곡선 저장: {filepath}")
        return filepath

    # ───────────────────────────────────────
    #  매매 지점 캔들 차트
    # ───────────────────────────────────────
    def plot_trades_on_chart(
        self,
        df: pd.DataFrame,
        trades: List[Dict],
        title: str = "매매 지점 차트",
        filename: str = "trade_chart.png",
    ) -> str:
        """
        OHLCV 캔들 차트에 매수/매도 지점 표시

        Args:
            df: OHLCV DataFrame (DatetimeIndex)
            trades: 거래 기록 목록

        Returns:
            저장된 파일 경로
        """
        # 매수/매도 마커 준비
        buy_markers = pd.Series(np.nan, index=df.index)
        sell_markers = pd.Series(np.nan, index=df.index)

        for trade in trades:
            entry_idx = trade.get("entry_idx")
            exit_idx = trade.get("exit_idx")
            if entry_idx is not None and entry_idx < len(df):
                buy_markers.iloc[entry_idx] = df.iloc[entry_idx]["low"] * 0.998
            if exit_idx is not None and exit_idx < len(df):
                sell_markers.iloc[exit_idx] = df.iloc[exit_idx]["high"] * 1.002

        add_plots = []
        if buy_markers.notna().any():
            add_plots.append(
                mpf.make_addplot(
                    buy_markers, type="scatter", marker="^",
                    markersize=80, color="green", panel=0,
                )
            )
        if sell_markers.notna().any():
            add_plots.append(
                mpf.make_addplot(
                    sell_markers, type="scatter", marker="v",
                    markersize=80, color="red", panel=0,
                )
            )

        filepath = str(self.output_dir / filename)

        mc = mpf.make_marketcolors(
            up="green", down="red",
            edge="inherit", volume="in",
        )
        style = mpf.make_mpf_style(marketcolors=mc, gridstyle="-", gridcolor="#e0e0e0")

        fig, _ = mpf.plot(
            df,
            type="candle",
            style=style,
            volume=True,
            addplot=add_plots if add_plots else None,
            title=title,
            figsize=(16, 8),
            returnfig=True,
        )

        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"매매 차트 저장: {filepath}")
        return filepath

    # ───────────────────────────────────────
    #  일별 PnL 히트맵/바 차트
    # ───────────────────────────────────────
    def plot_daily_pnl(
        self,
        daily_data: List[Dict],
        filename: str = "daily_pnl.png",
    ) -> str:
        """
        일별 손익 바 차트

        Args:
            daily_data: [{date, total_pnl_krw, ...}] 목록

        Returns:
            저장된 파일 경로
        """
        if not daily_data:
            logger.warning("일별 데이터 없음")
            return ""

        dates = [d["date"] for d in daily_data]
        pnls = [d.get("total_pnl_krw", 0) for d in daily_data]
        colors = ["#4CAF50" if p >= 0 else "#F44336" for p in pnls]

        fig, ax = plt.subplots(figsize=(14, 6))
        ax.bar(dates, pnls, color=colors, width=0.8)
        ax.set_title("일별 손익", fontsize=14, fontweight="bold")
        ax.set_xlabel("날짜")
        ax.set_ylabel("PnL (KRW)")
        ax.axhline(y=0, color="gray", linewidth=0.5)
        ax.grid(True, axis="y", alpha=0.3)
        plt.xticks(rotation=45)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        filepath = str(self.output_dir / filename)
        fig.tight_layout()
        fig.savefig(filepath, dpi=150, bbox_inches="tight")
        plt.close(fig)

        logger.info(f"일별 PnL 차트 저장: {filepath}")
        return filepath

    # ───────────────────────────────────────
    #  종합 성과 보고서
    # ───────────────────────────────────────
    def generate_report(
        self,
        equity_curve: List[float],
        trades: List[Dict],
        df: Optional[pd.DataFrame] = None,
        pair: str = "",
    ) -> List[str]:
        """
        종합 성과 차트 일괄 생성

        Returns:
            생성된 파일 경로 목록
        """
        files = []
        prefix = pair.replace("-", "_").lower() + "_" if pair else ""

        # 수익 곡선
        if equity_curve:
            f = self.plot_equity_curve(
                equity_curve,
                title=f"누적 수익 곡선 — {pair}" if pair else "누적 수익 곡선",
                filename=f"{prefix}equity_curve.png",
            )
            files.append(f)

        # 매매 차트
        if df is not None and trades:
            f = self.plot_trades_on_chart(
                df, trades,
                title=f"매매 지점 — {pair}" if pair else "매매 지점",
                filename=f"{prefix}trade_chart.png",
            )
            files.append(f)

        return files
