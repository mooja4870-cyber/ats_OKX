"""기술적 지표 계산 모듈"""
from __future__ import annotations

import pandas as pd
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    ta = None
    HAS_PANDAS_TA = False
import numpy as np
from loguru import logger


class Indicators:
    """EMA, RSI, 볼린저밴드, VWAP, 거래량 분석"""

    def __init__(self, config: dict):
        self.cfg = config["indicators"]
        self.ema_fast = self.cfg["ema_fast"]       # 9
        self.ema_slow = self.cfg["ema_slow"]       # 21
        self.rsi_period = self.cfg["rsi_period"]   # 14
        self.bb_period = self.cfg["bb_period"]     # 20
        self.bb_std = self.cfg["bb_std"]           # 2.0
        self.vol_mult = self.cfg["volume_multiplier"]  # 1.5
        self._use_pandas_ta = HAS_PANDAS_TA

    def _calculate_basic_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """pandas_ta 미사용 수동 지표 계산"""
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()

        # 간단한 RSI 계산
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period, min_periods=self.rsi_period).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # 볼린저 밴드
        df["bb_mid"] = df["close"].rolling(window=self.bb_period).mean()
        rolling_std = df["close"].rolling(window=self.bb_period).std()
        df["bb_upper"] = df["bb_mid"] + (self.bb_std * rolling_std)
        df["bb_lower"] = df["bb_mid"] - (self.bb_std * rolling_std)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
        df["bb_pctb"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # ATR 계산
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=self.rsi_period).mean()
        df["atr_pct"] = df["atr"] / df["close"]

        return df

    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """모든 지표를 한 번에 계산하여 DataFrame에 추가"""
        if df is None or df.empty:
            return df

        df = df.copy()

        try:
            if self._use_pandas_ta:
                # 1. EMA 9 / EMA 21
                try:
                    df["ema_fast"] = ta.ema(df["close"], length=self.ema_fast)
                    df["ema_slow"] = ta.ema(df["close"], length=self.ema_slow)

                    # 2. RSI (14)
                    df["rsi"] = ta.rsi(df["close"], length=self.rsi_period)

                    # 3. 볼린저 밴드 (20, 2σ)
                    bb = ta.bbands(df["close"], length=self.bb_period, std=self.bb_std)
                    if bb is not None:
                        df["bb_lower"] = bb.iloc[:, 0]   # BBL
                        df["bb_mid"] = bb.iloc[:, 1]     # BBM
                        df["bb_upper"] = bb.iloc[:, 2]   # BBU
                        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
                        # %B 지표 (0=하단, 1=상단)
                        df["bb_pctb"] = (df["close"] - df["bb_lower"]) / (
                            df["bb_upper"] - df["bb_lower"]
                        )
                    
                    # 4. ATR (14)
                    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=self.rsi_period)
                    df["atr_pct"] = df["atr"] / df["close"]

                except Exception as e:
                    # pandas/pandas_ta 버전 호환성 이슈 발생 시 자동으로 수동 계산으로 고정
                    self._use_pandas_ta = False
                    logger.warning(f"[Indicators] pandas_ta 비활성화 후 fallback 사용: {e}")
                    df = self._calculate_basic_indicators(df)
            else:
                df = self._calculate_basic_indicators(df)

            # EMA 크로스 판별
            df["ema_cross"] = 0
            ema_diff = df["ema_fast"] - df["ema_slow"]
            ema_diff_prev = ema_diff.shift(1)
            # 골든크로스: 이전 음수 → 현재 양수
            df.loc[(ema_diff_prev <= 0) & (ema_diff > 0), "ema_cross"] = 1
            # 데드크로스: 이전 양수 → 현재 음수
            df.loc[(ema_diff_prev >= 0) & (ema_diff < 0), "ema_cross"] = -1
            # EMA 상태: fast > slow → True
            df["ema_bullish"] = df["ema_fast"] > df["ema_slow"]

            # 4. VWAP (당일 누적)
            df["vwap"] = self._calculate_vwap(df)

            # 5. 거래량 분석
            df["vol_ma"] = df["volume"].rolling(window=20).mean()
            df["vol_ratio"] = df["volume"] / df["vol_ma"]
            df["vol_surge"] = df["vol_ratio"] >= self.vol_mult

            # NaN 제거 (초반 지표 미계산 구간)
            # 주의: dropna 하지 않고, 최신 데이터만 사용하도록 설계

            logger.debug(
                f"[Indicators] 지표 계산 완료 — "
                f"RSI: {df['rsi'].iloc[-1]:.1f}, "
                f"EMA: {'▲' if df['ema_bullish'].iloc[-1] else '▼'}, "
                f"Vol: {df['vol_ratio'].iloc[-1]:.1f}x"
            )

        except Exception as e:
            logger.error(f"[Indicators] 지표 계산 오류: {e}")

        return df

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """VWAP 계산 (당일 기준 누적)"""
        try:
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            
            # Reset VWAP daily if we have datetime index
            if isinstance(df.index, pd.DatetimeIndex):
                dates = df.index.date
                vwap = pd.Series(np.nan, index=df.index, dtype=float)
                for date in pd.unique(dates):
                    mask = dates == date
                    tp_vol = (typical_price[mask] * df["volume"][mask]).cumsum()
                    vol_cum = df["volume"][mask].cumsum()
                    vwap[mask] = tp_vol / vol_cum.replace(0, np.nan)
            else:
                cum_vol = df["volume"].cumsum()
                cum_tp_vol = (typical_price * df["volume"]).cumsum()
                vwap = cum_tp_vol / cum_vol
                vwap = vwap.replace([np.inf, -np.inf], np.nan)
            return vwap
        except Exception as e:
            logger.error(f"[Indicators] VWAP 계산 오류: {e}")
            return pd.Series(np.nan, index=df.index)

    def get_latest_summary(self, df: pd.DataFrame) -> dict:
        """최신 봉의 지표 요약 반환"""
        if df is None or df.empty:
            return {}

        latest = df.iloc[-1]
        return {
            "close": latest.get("close"),
            "ema_fast": latest.get("ema_fast"),
            "ema_slow": latest.get("ema_slow"),
            "ema_bullish": latest.get("ema_bullish"),
            "ema_cross": latest.get("ema_cross"),
            "rsi": latest.get("rsi"),
            "bb_upper": latest.get("bb_upper"),
            "bb_mid": latest.get("bb_mid"),
            "bb_lower": latest.get("bb_lower"),
            "bb_pctb": latest.get("bb_pctb"),
            "atr": latest.get("atr"),
            "atr_pct": latest.get("atr_pct"),
            "vwap": latest.get("vwap"),
            "vol_ratio": latest.get("vol_ratio"),
            "vol_surge": latest.get("vol_surge"),
        }
