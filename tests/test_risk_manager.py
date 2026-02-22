"""
테스트 — 리스크 관리 모듈
"""

import pytest

from src.core.risk_manager import RiskManager


@pytest.fixture
def config():
    return {
        "risk": {
            "risk_per_trade_pct": 0.004,
            "max_daily_loss_pct": 0.01,
            "max_consecutive_losses": 2,
            "fee_rate": 0.0005,
            "emergency_drop_pct": 0.03,
            "min_expected_move_pct": 0.01,
        },
        "trading": {},
    }


@pytest.fixture
def rm(config):
    return RiskManager(config, 10000.0)


class TestCanTrade:
    def test_initial_can_trade(self, rm):
        assert rm.can_trade(1_000_000) is True

    def test_max_trades_exceeded(self, rm):
        for _ in range(7):
            rm.record_trade_result(1000, 0.001, "KRW-BTC", "take_profit")
        assert rm.can_trade(1_000_000) is False

    def test_consecutive_losses(self, rm):
        rm.record_trade_result(-1000, -0.001, "KRW-BTC", "stop_loss")
        assert rm.can_trade(1_000_000) is True

        rm.record_trade_result(-1000, -0.001, "KRW-BTC", "stop_loss")
        assert rm.can_trade(1_000_000) is False  # 2연패

    def test_consecutive_loss_reset_on_win(self, rm):
        rm.record_trade_result(-1000, -0.001, "KRW-BTC", "stop_loss")
        rm.record_trade_result(500, 0.0005, "KRW-BTC", "take_profit")
        # 연패 리셋됨
        assert rm.can_trade(1_000_000) is True

    def test_daily_loss_limit(self, rm):
        # 잔고 100만원에서 1% = 1만원
        balance = 1_000_000
        rm.record_trade_result(-5000, -0.005, "KRW-BTC", "stop_loss")
        assert rm.can_trade(balance) is True

        rm.record_trade_result(-6000, -0.006, "KRW-BTC", "stop_loss")
        # 누적 손실 11000원 > 10000원(1%)
        assert rm.can_trade(balance) is False


class TestEmergencyStop:
    def test_no_emergency_normal(self, rm):
        import pandas as pd
        import numpy as np

        prices = [100, 100.5, 101, 100.8, 101.2]
        df = pd.DataFrame({
            "close": prices,
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "volume": [1000] * 5,
        })
        assert rm.check_emergency(df) is False

    def test_emergency_on_crash(self, rm):
        import pandas as pd

        # 3% 급락
        prices = [100, 99, 98, 97.5, 96.9]
        df = pd.DataFrame({
            "close": prices,
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "volume": [1000] * 5,
        })
        assert rm.check_emergency(df) is True
        assert rm.is_stopped is True


class TestManualControl:
    def test_emergency_stop(self, rm):
        rm.emergency_stop("수동 정지")
        assert rm.is_stopped is True
        assert rm.can_trade(1_000_000) is False

    def test_resume(self, rm):
        rm.emergency_stop("테스트")
        rm.resume()
        assert rm.is_stopped is False
        assert rm.can_trade(1_000_000) is True


class TestRecordResult:
    def test_win_record(self, rm):
        rm.record_trade_result(1000, 0.001, "KRW-BTC", "take_profit")
        summary = rm.get_daily_summary()
        assert summary["total_trades"] == 1
        assert summary["wins"] == 1
        assert summary["losses"] == 0
        assert summary["daily_pnl_krw"] == 1000

    def test_loss_record(self, rm):
        rm.record_trade_result(-500, -0.0005, "KRW-BTC", "stop_loss")
        summary = rm.get_daily_summary()
        assert summary["total_trades"] == 1
        assert summary["wins"] == 0
        assert summary["losses"] == 1
        assert summary["daily_pnl_krw"] == -500


class TestFeeCalculation:
    def test_single_fee(self, rm):
        fee = rm.calc_fee(1_000_000)
        assert fee == 500  # 0.05%

    def test_round_trip_fee(self, rm):
        fee = rm.calc_round_trip_fee(1_000_000)
        assert fee == 1000  # 0.1%


class TestPositionValidation:
    def test_valid_position(self, rm):
        assert rm.validate_position_size(4000, 1_000_000) is True

    def test_oversized_position(self, rm):
        assert rm.validate_position_size(5_000_000, 1_000_000) is False
