"""
테스트 — 매매 신호 엔진 로직
"""

import pandas as pd
import numpy as np
import pytest

from src.core.signal_engine import SignalEngine


@pytest.fixture
def config():
    return {
        "indicators": {
            "rsi_buy_min": 40,
            "rsi_buy_max": 55,
            "volume_multiplier": 1.5,
        },
        "signal": {
            "min_score": 70,
            "cooldown_minutes": 5,
            "confirm_on_close": True,
        },
        "risk": {
            "stop_loss_pct": 0.008,
            "take_profit_btc_pct": 0.007,
            "take_profit_alt_pct": 0.012,
        },
        "trading": {
            "max_hold_minutes": 60,
        },
        "schedule": {
            "sessions": [
                {"name": "테스트", "start": "00:00", "end": "23:59"},
            ],
            "no_entry_before_end_minutes": 0,
        },
    }


@pytest.fixture
def engine(config):
    return SignalEngine(config)


def make_df(
    ema_fast=101, ema_slow=100, rsi=47, close=105,
    bb_mid=100, vol_ratio=2.0, vwap=100, rows=5,
):
    """조건 충족하는 기본 DataFrame 생성"""
    data = {
        "close": [close] * rows,
        "open": [close] * rows,
        "high": [close + 1] * rows,
        "low": [close - 1] * rows,
        "volume": [1000] * rows,
        "ema_fast": [ema_fast] * rows,
        "ema_slow": [ema_slow] * rows,
        "rsi": [rsi] * rows,
        "bb_mid": [bb_mid] * rows,
        "vol_ratio": [vol_ratio] * rows,
        "vwap": [vwap] * rows,
    }
    return pd.DataFrame(data)


class TestBuySignal:
    def test_all_conditions_met(self, engine):
        df_5m = make_df()
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert signal is True
        assert score >= 70
        assert all(conditions.values())

    def test_ema_not_crossed(self, engine):
        df_5m = make_df(ema_fast=99, ema_slow=100)  # dead
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["ema_cross"] is False

    def test_rsi_too_high(self, engine):
        df_5m = make_df(rsi=60)  # 과매수
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["rsi_range"] is False

    def test_rsi_too_low(self, engine):
        df_5m = make_df(rsi=30)  # 과매도
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["rsi_range"] is False

    def test_below_bb_mid(self, engine):
        df_5m = make_df(close=99, bb_mid=100)
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["above_bb_mid"] is False

    def test_low_volume(self, engine):
        df_5m = make_df(vol_ratio=1.0)  # 평균 이하
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["volume_surge"] is False

    def test_below_vwap(self, engine):
        df_5m = make_df(close=99, vwap=100)
        df_1h = make_df()
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["above_vwap"] is False

    def test_hourly_trend_bearish(self, engine):
        df_5m = make_df()
        df_1h = make_df(ema_fast=99, ema_slow=100)  # 1h bearish
        signal, score, conditions = engine.check_buy_signal(df_5m, df_1h)
        assert conditions["trend_ok"] is False

    def test_empty_dataframe(self, engine):
        signal, score, conditions = engine.check_buy_signal(pd.DataFrame(), pd.DataFrame())
        assert signal is False


class TestSellSignal:
    def test_take_profit(self, engine):
        df_5m = make_df(close=101)
        position = {
            "entry_price": 100,
            "target_price": 100.7,
            "stop_price": 99.2,
            "entry_time": None,
        }
        signal, reason = engine.check_sell_signal(df_5m, position)
        assert signal is True
        assert reason == "take_profit"

    def test_stop_loss(self, engine):
        df_5m = make_df(close=99)
        position = {
            "entry_price": 100,
            "target_price": 100.7,
            "stop_price": 99.2,
            "entry_time": None,
        }
        signal, reason = engine.check_sell_signal(df_5m, position)
        assert signal is True
        assert reason == "stop_loss"

    def test_no_sell(self, engine):
        df_5m = make_df(close=100.3, ema_fast=101, ema_slow=100)
        position = {
            "entry_price": 100,
            "target_price": 100.7,
            "stop_price": 99.2,
            "entry_time": None,
        }
        signal, reason = engine.check_sell_signal(df_5m, position)
        assert signal is False


class TestSignalScore:
    def test_all_met_score(self, engine):
        conditions = {
            "ema_cross": True,
            "rsi_range": True,
            "above_bb_mid": True,
            "volume_surge": True,
            "above_vwap": True,
            "trend_ok": True,
        }
        score = engine.calc_signal_score(conditions)
        assert score == 100

    def test_none_met_score(self, engine):
        conditions = {
            "ema_cross": False,
            "rsi_range": False,
            "above_bb_mid": False,
            "volume_surge": False,
            "above_vwap": False,
            "trend_ok": False,
        }
        score = engine.calc_signal_score(conditions)
        assert score == 0

    def test_partial_score(self, engine):
        conditions = {
            "ema_cross": True,     # 20
            "rsi_range": True,     # 15
            "above_bb_mid": False,
            "volume_surge": False,
            "above_vwap": False,
            "trend_ok": False,
        }
        score = engine.calc_signal_score(conditions)
        assert score == 35


class TestTargets:
    def test_btc_targets(self, engine):
        target, stop = engine.calc_targets(100_000_000, "KRW-BTC")
        assert target == 100_000_000 * 1.007
        assert stop == 100_000_000 * 0.992

    def test_alt_targets(self, engine):
        target, stop = engine.calc_targets(1000, "KRW-XRP")
        assert target == 1000 * 1.012
        assert stop == 1000 * 0.992
