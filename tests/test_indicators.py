"""
테스트 — 기술적 지표 계산 정확성
"""

import numpy as np
import pandas as pd
import pytest

from src.core.indicators import Indicators


@pytest.fixture
def sample_ohlcv():
    """테스트용 OHLCV 데이터 생성"""
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="5min")

    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.abs(np.random.randn(n) * 1000) + 500

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)

    return df


@pytest.fixture
def indicators():
    config = {
        "indicators": {
            "ema_fast": 9,
            "ema_slow": 21,
            "rsi_period": 14,
            "bb_period": 20,
            "bb_std": 2.0,
            "volume_multiplier": 1.5,
        }
    }
    return Indicators(config)


class TestEMA:
    def test_ema_returns_series(self, indicators, sample_ohlcv):
        ema = indicators.calc_ema(sample_ohlcv, 9)
        assert isinstance(ema, pd.Series)
        assert len(ema) == len(sample_ohlcv)

    def test_ema_values_reasonable(self, indicators, sample_ohlcv):
        ema = indicators.calc_ema(sample_ohlcv, 9)
        # EMA는 가격 범위 내에 있어야 함
        assert ema.dropna().min() > sample_ohlcv["close"].min() - 10
        assert ema.dropna().max() < sample_ohlcv["close"].max() + 10

    def test_ema_fast_more_responsive(self, indicators, sample_ohlcv):
        ema_fast = indicators.calc_ema(sample_ohlcv, 9)
        ema_slow = indicators.calc_ema(sample_ohlcv, 21)
        # Fast EMA가 최신 가격에 더 가까워야 함
        last_price = sample_ohlcv["close"].iloc[-1]
        assert abs(ema_fast.iloc[-1] - last_price) <= abs(ema_slow.iloc[-1] - last_price) + 5


class TestRSI:
    def test_rsi_range(self, indicators, sample_ohlcv):
        rsi = indicators.calc_rsi(sample_ohlcv)
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()

    def test_rsi_returns_series(self, indicators, sample_ohlcv):
        rsi = indicators.calc_rsi(sample_ohlcv)
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_ohlcv)


class TestBollinger:
    def test_bb_returns_dataframe(self, indicators, sample_ohlcv):
        bb = indicators.calc_bollinger(sample_ohlcv)
        assert isinstance(bb, pd.DataFrame)
        assert "bb_upper" in bb.columns
        assert "bb_mid" in bb.columns
        assert "bb_lower" in bb.columns

    def test_bb_order(self, indicators, sample_ohlcv):
        bb = indicators.calc_bollinger(sample_ohlcv)
        valid = bb.dropna()
        assert (valid["bb_upper"] >= valid["bb_mid"]).all()
        assert (valid["bb_mid"] >= valid["bb_lower"]).all()


class TestVWAP:
    def test_vwap_returns_series(self, indicators, sample_ohlcv):
        vwap = indicators.calc_vwap(sample_ohlcv)
        assert isinstance(vwap, pd.Series)
        assert len(vwap) == len(sample_ohlcv)

    def test_vwap_within_price_range(self, indicators, sample_ohlcv):
        vwap = indicators.calc_vwap(sample_ohlcv)
        valid = vwap.dropna()
        assert valid.min() >= sample_ohlcv["low"].min() - 1
        assert valid.max() <= sample_ohlcv["high"].max() + 1


class TestVolumeRatio:
    def test_vol_ratio_returns_series(self, indicators, sample_ohlcv):
        ratio = indicators.calc_volume_ratio(sample_ohlcv)
        assert isinstance(ratio, pd.Series)

    def test_vol_ratio_positive(self, indicators, sample_ohlcv):
        ratio = indicators.calc_volume_ratio(sample_ohlcv)
        valid = ratio.dropna()
        assert (valid >= 0).all()


class TestCalculateAll:
    def test_all_columns_present(self, indicators, sample_ohlcv):
        result = indicators.calculate_all(sample_ohlcv)
        expected_cols = [
            "ema_fast", "ema_slow", "rsi",
            "bb_upper", "bb_mid", "bb_lower",
            "vwap", "vol_ratio", "ema_cross",
        ]
        for col in expected_cols:
            assert col in result.columns, f"컬럼 누락: {col}"

    def test_original_columns_preserved(self, indicators, sample_ohlcv):
        result = indicators.calculate_all(sample_ohlcv)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_empty_dataframe(self, indicators):
        result = indicators.calculate_all(pd.DataFrame())
        assert result is not None


class TestEMACross:
    def test_cross_values(self, indicators, sample_ohlcv):
        result = indicators.calculate_all(sample_ohlcv)
        cross = result["ema_cross"]
        valid_values = {-1, 0, 1}
        assert set(cross.dropna().unique()).issubset(valid_values)
