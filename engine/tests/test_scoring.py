"""
CryptoAI Master — 멀티팩터 스코어링 엔진 테스트
================================================

pytest를 사용한 단위 테스트.
실행: pytest engine/tests/test_scoring.py -v
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from engine.layer3_strategy.multi_factor_scoring import (
    FactorDetail,
    MultiFactorScoring,
    ScoringResult,
    _clamp,
)


# ═══════════════════════════════════════════════════
# Mock DB Manager
# ═══════════════════════════════════════════════════

class MockDBManager:
    """테스트용 Mock 데이터베이스 매니저.

    다양한 시장 시나리오를 시뮬레이션합니다.
    """

    # ── 사전 정의된 시나리오 ──

    SCENARIOS: Dict[str, Dict[str, Any]] = {
        # 🟢 BTC — 강력 매수 시나리오 (과매도 + 거래량 폭발)
        "BTC": {
            "indicators": {
                "current_price": 143_250_000,
                "open_price": 147_000_000,      # -2.55% 소폭 조정
                "rsi_14": 25.3,                  # 과매도
                "macd_histogram": 125_000,        # 양전환
                "macd_signal": -50_000,           # 시그널 음수 → 골든크로스
                "bollinger_lower": 140_000_000,
                "bollinger_upper": 155_000_000,   # 하단 근접
                "sma_5": 145_000_000,
                "sma_20": 143_000_000,
                "sma_60": 140_000_000,            # 정배열
                "ema_12": 144_000_000,
                "ema_26": 142_500_000,
                "adx": 42.0,                     # 강한 추세
                "stoch_k": 18.0,                  # 과매도
                "stoch_d": 22.0,
                "roc_12": -3.5,                   # 하락 후 반등 기대
                "cci_20": -150,                   # 과매도
                "volume_ratio": 3.2,              # 거래량 높음
                "obv_trend": "RISING",            # 매집
                "vwap": 144_500_000,
            },
            "volatility": {
                "volatility_regime": "MEDIUM",
                "atr_percent": 2.1,
                "bb_width": 0.04,
            },
        },
        # 🟡 ETH — 관망 시나리오 (혼조)
        "ETH": {
            "indicators": {
                "current_price": 4_800_000,
                "open_price": 4_780_000,
                "rsi_14": 52.0,                   # 중립
                "macd_histogram": -5_000,          # 약한 음
                "macd_signal": 3_000,
                "bollinger_lower": 4_600_000,
                "bollinger_upper": 5_000_000,
                "sma_5": 4_810_000,
                "sma_20": 4_790_000,
                "sma_60": 4_820_000,               # 혼조 배열
                "ema_12": 4_795_000,
                "ema_26": 4_800_000,
                "adx": 18.0,                      # 추세 약함
                "stoch_k": 55.0,
                "stoch_d": 53.0,
                "roc_12": 0.5,
                "cci_20": 10,
                "volume_ratio": 0.9,               # 평균 수준
                "obv_trend": "NEUTRAL",
                "vwap": 4_790_000,
            },
            "volatility": {
                "volatility_regime": "LOW",
                "atr_percent": 0.8,
                "bb_width": 0.015,
            },
        },
        # 🟢 SOL — 매수 시나리오
        "SOL": {
            "indicators": {
                "current_price": 285_000,
                "open_price": 290_000,             # 소폭 조정
                "rsi_14": 33.0,                    # 약 과매도
                "macd_histogram": 800,
                "macd_signal": -200,               # 골든크로스
                "bollinger_lower": 278_000,
                "bollinger_upper": 300_000,
                "sma_5": 288_000,
                "sma_20": 285_000,
                "sma_60": 280_000,                 # 정배열
                "ema_12": 286_000,
                "ema_26": 284_000,
                "adx": 30.0,
                "stoch_k": 28.0,                   # 약간 과매도
                "stoch_d": 32.0,
                "roc_12": -1.5,
                "cci_20": -80,
                "volume_ratio": 2.1,               # 높은 거래량
                "obv_trend": "RISING",
                "vwap": 287_000,
            },
            "volatility": {
                "volatility_regime": "MEDIUM",
                "atr_percent": 2.8,
                "bb_width": 0.045,
            },
        },
        # 🔴 XRP — 매도 시나리오 (과매수 + 거래량 감소)
        "XRP": {
            "indicators": {
                "current_price": 3_500,
                "open_price": 3_300,               # +6% 급등
                "rsi_14": 82.0,                    # 과매수
                "macd_histogram": -15,
                "macd_signal": 10,                 # 데드크로스
                "bollinger_lower": 3_100,
                "bollinger_upper": 3_400,           # 상단 이탈!
                "sma_5": 3_350,
                "sma_20": 3_400,
                "sma_60": 3_300,
                "ema_12": 3_380,
                "ema_26": 3_420,                    # EMA 역전환
                "adx": 22.0,
                "stoch_k": 88.0,                   # 극도 과매수
                "stoch_d": 85.0,
                "roc_12": 12.0,                    # 과열
                "cci_20": 220,                     # 극도 과매수
                "volume_ratio": 0.4,               # 거래 감소
                "obv_trend": "FALLING",
                "vwap": 3_300,
            },
            "volatility": {
                "volatility_regime": "HIGH",
                "atr_percent": 4.5,
                "bb_width": 0.085,
            },
        },
    }

    SENTIMENT = {
        "fear_greed_index": 22,       # 공포 구간
        "news_sentiment": 0.3,
        "social_volume_change": 45.0,
    }

    def __init__(self, scenario_overrides: Optional[Dict] = None):
        self.stored_results: List[ScoringResult] = []
        self.overrides = scenario_overrides or {}

    def get_latest_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        data = self.overrides.get(symbol, self.SCENARIOS.get(symbol, {}))
        return data.get("indicators")

    def get_latest_volatility(self, symbol: str) -> Optional[Dict[str, Any]]:
        data = self.overrides.get(symbol, self.SCENARIOS.get(symbol, {}))
        return data.get("volatility")

    def get_latest_sentiment(self) -> Optional[Dict[str, Any]]:
        return self.overrides.get("sentiment", self.SENTIMENT)

    def insert_scoring_result(self, result: ScoringResult) -> None:
        self.stored_results.append(result)


# ═══════════════════════════════════════════════════
# 테스트: 유틸리티
# ═══════════════════════════════════════════════════

class TestClamp:
    """_clamp 함수 테스트."""

    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_minimum(self):
        assert _clamp(-10.0) == 0.0

    def test_above_maximum(self):
        assert _clamp(150.0) == 100.0

    def test_boundary_values(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 10.0, 20.0) == 10.0
        assert _clamp(25.0, 10.0, 20.0) == 20.0


# ═══════════════════════════════════════════════════
# 테스트: 초기화 & 설정
# ═══════════════════════════════════════════════════

class TestInitialization:
    """MultiFactorScoring 초기화 테스트."""

    def test_default_weights(self):
        db = MockDBManager()
        scorer = MultiFactorScoring(db_manager=db)
        assert sum(scorer.weights.values()) == pytest.approx(1.0)

    def test_custom_weights(self):
        db = MockDBManager()
        custom = {
            "technical": 0.40,
            "momentum": 0.20,
            "volatility": 0.15,
            "volume": 0.15,
            "sentiment": 0.10,
        }
        scorer = MultiFactorScoring(db_manager=db, weights=custom)
        assert scorer.weights["technical"] == 0.40

    def test_invalid_weights_raises(self):
        db = MockDBManager()
        bad_weights = {
            "technical": 0.50,
            "momentum": 0.50,
            "volatility": 0.15,
            "volume": 0.15,
            "sentiment": 0.15,
        }
        with pytest.raises(ValueError, match="합계"):
            MultiFactorScoring(db_manager=db, weights=bad_weights)

    def test_custom_thresholds(self):
        db = MockDBManager()
        scorer = MultiFactorScoring(
            db_manager=db,
            buy_threshold=65,
            strong_buy_threshold=85,
            sell_threshold=25,
        )
        assert scorer.buy_threshold == 65
        assert scorer.strong_buy_threshold == 85


# ═══════════════════════════════════════════════════
# 테스트: 개별 팩터 계산
# ═══════════════════════════════════════════════════

class TestTechnicalScore:
    """기술적 분석 팩터 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_oversold_rsi_boosts_score(self, scorer):
        ind = {"rsi_14": 20.0, "current_price": 100}
        score, details = scorer._calc_technical_score(ind)
        assert score >= 70
        rsi_detail = details[0]
        assert rsi_detail.name == "RSI(14)"
        assert rsi_detail.contribution > 0

    def test_overbought_rsi_reduces_score(self, scorer):
        ind = {"rsi_14": 88.0, "current_price": 100}
        score, details = scorer._calc_technical_score(ind)
        assert score < 30

    def test_golden_cross_macd(self, scorer):
        ind = {"rsi_14": 50, "macd_histogram": 100, "macd_signal": -50}
        score, details = scorer._calc_technical_score(ind)
        macd_detail = [d for d in details if "MACD" in d.name][0]
        assert macd_detail.contribution == 15.0

    def test_perfect_alignment_sma(self, scorer):
        ind = {
            "rsi_14": 50, "sma_5": 105, "sma_20": 100, "sma_60": 95,
            "current_price": 100,
        }
        score, details = scorer._calc_technical_score(ind)
        ma_detail = [d for d in details if "이동평균" in d.name][0]
        assert ma_detail.contribution == 12.0

    def test_score_always_in_range(self, scorer):
        # 극단 케이스: 모든 지표 최악
        ind = {
            "rsi_14": 95, "macd_histogram": -1000, "macd_signal": 500,
            "current_price": 200, "bollinger_lower": 100, "bollinger_upper": 150,
            "sma_5": 80, "sma_20": 90, "sma_60": 100, "adx": 10,
        }
        score, _ = scorer._calc_technical_score(ind)
        assert 0 <= score <= 100


class TestMomentumScore:
    """모멘텀 팩터 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_small_dip_is_bullish(self, scorer):
        ind = {"current_price": 97, "open_price": 100, "stoch_k": 50, "stoch_d": 50}
        score, details = scorer._calc_momentum_score(ind)
        gap_detail = details[0]
        assert gap_detail.contribution > 0  # 소폭 조정 → 매수 기회

    def test_crash_is_bearish(self, scorer):
        ind = {"current_price": 85, "open_price": 100, "stoch_k": 50, "stoch_d": 50}
        score, details = scorer._calc_momentum_score(ind)
        gap_detail = details[0]
        assert gap_detail.contribution < 0

    def test_oversold_stochastic(self, scorer):
        ind = {"current_price": 100, "open_price": 100, "stoch_k": 10, "stoch_d": 15}
        score, details = scorer._calc_momentum_score(ind)
        stoch_detail = [d for d in details if "스토캐스틱" in d.name][0]
        assert stoch_detail.contribution > 0


class TestVolatilityScore:
    """변동성 팩터 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_medium_volatility_is_optimal(self, scorer):
        vol = {"volatility_regime": "MEDIUM", "atr_percent": 2.0, "bb_width": 0.04}
        score, _ = scorer._calc_volatility_score(vol)
        assert score >= 75  # MEDIUM 은 최적

    def test_extreme_volatility_is_dangerous(self, scorer):
        vol = {"volatility_regime": "EXTREME", "atr_percent": 8.0, "bb_width": 0.15}
        score, _ = scorer._calc_volatility_score(vol)
        assert score < 40

    def test_none_returns_neutral(self, scorer):
        score, _ = scorer._calc_volatility_score(None)
        assert score == 50.0


class TestVolumeScore:
    """거래량 팩터 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_volume_explosion(self, scorer):
        ind = {"volume_ratio": 5.5, "obv_trend": "RISING", "current_price": 0}
        score, _ = scorer._calc_volume_score(ind)
        assert score >= 85

    def test_volume_dry_up(self, scorer):
        ind = {"volume_ratio": 0.2, "obv_trend": "FALLING", "current_price": 0}
        score, _ = scorer._calc_volume_score(ind)
        assert score < 30


class TestSentimentScore:
    """감성 팩터 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_extreme_fear_is_bullish(self, scorer):
        sent = {"fear_greed_index": 10, "news_sentiment": 0.0, "social_volume_change": 0}
        score, _ = scorer._calc_sentiment_score(sent)
        assert score >= 75  # 역발상: 공포 시 매수

    def test_extreme_greed_is_bearish(self, scorer):
        sent = {"fear_greed_index": 90, "news_sentiment": 0.0, "social_volume_change": 0}
        score, _ = scorer._calc_sentiment_score(sent)
        assert score < 35

    def test_none_returns_neutral(self, scorer):
        score, _ = scorer._calc_sentiment_score(None)
        assert score == 50.0


# ═══════════════════════════════════════════════════
# 테스트: 종합 스코어링
# ═══════════════════════════════════════════════════

class TestScoreCoin:
    """단일 코인 스코어링 통합 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_btc_strong_buy(self, scorer):
        result = scorer.score_coin("BTC")
        assert result.signal in ("STRONG_BUY", "BUY")
        assert result.total_score >= 70
        assert result.confidence > 0
        assert len(result.reasoning) > 0

    def test_eth_hold(self, scorer):
        result = scorer.score_coin("ETH")
        assert result.signal == "HOLD"
        assert 31 <= result.total_score <= 69

    def test_xrp_sell(self, scorer):
        result = scorer.score_coin("XRP")
        assert result.signal in ("SELL", "HOLD")
        assert result.total_score <= 50

    def test_sol_buy(self, scorer):
        result = scorer.score_coin("SOL")
        assert result.signal in ("BUY", "STRONG_BUY")

    def test_missing_data_raises(self, scorer):
        with pytest.raises(ValueError, match="데이터가 없습니다"):
            scorer.score_coin("DOGE")

    def test_result_saved_to_db(self):
        db = MockDBManager()
        scorer = MultiFactorScoring(db_manager=db)
        scorer.score_coin("BTC")
        assert len(db.stored_results) == 1
        assert db.stored_results[0].symbol == "BTC"

    def test_result_has_details(self, scorer):
        result = scorer.score_coin("BTC")
        assert "technical" in result.details
        assert "momentum" in result.details
        assert len(result.details["technical"]) > 0

    def test_result_to_dict(self, scorer):
        result = scorer.score_coin("BTC")
        d = result.to_dict()
        assert isinstance(d["timestamp"], str)
        assert d["symbol"] == "BTC"

    def test_result_str_format(self, scorer):
        result = scorer.score_coin("BTC")
        s = str(result)
        assert "BTC" in s
        assert "█" in s


class TestScoreAllCoins:
    """전체 코인 스코어링 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_returns_sorted_by_score(self, scorer):
        results = scorer.score_all_coins(["BTC", "ETH", "XRP", "SOL"])
        scores = [r.total_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_all_four_coins(self, scorer):
        results = scorer.score_all_coins(["BTC", "ETH", "XRP", "SOL"])
        assert len(results) == 4

    def test_skips_unknown_coins(self, scorer):
        results = scorer.score_all_coins(["BTC", "DOGE", "ETH"])
        assert len(results) == 2  # DOGE skip


class TestGetBuyCandidates:
    """매수 후보 필터링 테스트."""

    def test_filters_only_buy_signals(self):
        db = MockDBManager()
        scorer = MultiFactorScoring(db_manager=db)
        candidates = scorer.get_buy_candidates(["BTC", "ETH", "XRP", "SOL"])
        for c in candidates:
            assert c.signal in ("BUY", "STRONG_BUY")


# ═══════════════════════════════════════════════════
# 테스트: 시그널 & 신뢰도
# ═══════════════════════════════════════════════════

class TestSignalDetermination:
    """시그널 결정 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_strong_buy(self, scorer):
        assert scorer._determine_signal(85) == "STRONG_BUY"

    def test_buy(self, scorer):
        assert scorer._determine_signal(75) == "BUY"

    def test_hold(self, scorer):
        assert scorer._determine_signal(50) == "HOLD"

    def test_sell(self, scorer):
        assert scorer._determine_signal(25) == "SELL"

    def test_boundary_80(self, scorer):
        assert scorer._determine_signal(80) == "STRONG_BUY"

    def test_boundary_70(self, scorer):
        assert scorer._determine_signal(70) == "BUY"

    def test_boundary_30(self, scorer):
        assert scorer._determine_signal(30) == "SELL"


class TestConfidence:
    """신뢰도 계산 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_high_consistency_high_confidence(self, scorer):
        # 모든 팩터가 비슷한 점수 → 높은 일관성
        scores = [80, 82, 78, 81, 79]
        conf = scorer._calc_confidence(80, scores)
        assert conf > 60

    def test_low_consistency_lower_confidence(self, scorer):
        # 팩터 간 큰 편차 → 낮은 일관성
        scores = [90, 20, 80, 30, 70]
        conf = scorer._calc_confidence(58, scores)
        assert conf < 70

    def test_always_in_range(self, scorer):
        conf = scorer._calc_confidence(50, [100, 0, 50, 50, 50])
        assert 0 <= conf <= 100


# ═══════════════════════════════════════════════════
# 테스트: 한글 설명 생성
# ═══════════════════════════════════════════════════

class TestReasoning:
    """한글 설명 생성 테스트."""

    @pytest.fixture
    def scorer(self):
        return MultiFactorScoring(db_manager=MockDBManager())

    def test_strong_buy_reasoning(self, scorer):
        reasoning = scorer._generate_reasoning(
            "BTC", 85, 80, 75, 70, 77, "STRONG_BUY"
        )
        assert "BTC" in reasoning
        assert "강력 매수" in reasoning
        assert "여러 팩터" in reasoning

    def test_hold_reasoning(self, scorer):
        reasoning = scorer._generate_reasoning(
            "ETH", 50, 55, 45, 48, 52, "HOLD"
        )
        assert "관망" in reasoning

    def test_sell_includes_warnings(self, scorer):
        reasoning = scorer._generate_reasoning(
            "XRP", 30, 25, 35, 28, 40, "SELL"
        )
        assert "매도" in reasoning


# ═══════════════════════════════════════════════════
# 테스트: ScoringResult 데이터 클래스
# ═══════════════════════════════════════════════════

class TestScoringResult:
    """ScoringResult 데이터 클래스 테스트."""

    def test_creation(self):
        result = ScoringResult(
            symbol="BTC",
            technical_score=85.0,
            momentum_score=78.0,
            volatility_score=72.0,
            volume_score=80.0,
            sentiment_score=75.0,
            total_score=80.5,
            signal="STRONG_BUY",
            confidence=87.3,
            reasoning="테스트",
        )
        assert result.symbol == "BTC"
        assert result.signal == "STRONG_BUY"

    def test_to_dict_serializable(self):
        result = ScoringResult(
            symbol="ETH",
            technical_score=50.0,
            momentum_score=50.0,
            volatility_score=50.0,
            volume_score=50.0,
            sentiment_score=50.0,
            total_score=50.0,
            signal="HOLD",
            confidence=50.0,
            reasoning="테스트",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert isinstance(d["timestamp"], str)


# ═══════════════════════════════════════════════════
# 샘플 실행 (pytest -s 로 출력 확인)
# ═══════════════════════════════════════════════════

class TestSampleExecution:
    """샘플 실행 — 4개 코인 스코어링 결과 출력."""

    def test_print_all_results(self, capsys):
        """전체 코인 스코어링 결과를 출력합니다.

        실행: pytest engine/tests/test_scoring.py::TestSampleExecution -vs
        """
        db = MockDBManager()
        scorer = MultiFactorScoring(db_manager=db)
        results = scorer.score_all_coins(["BTC", "ETH", "XRP", "SOL"])

        print("\n")
        print("=" * 70)
        print("  🧠 CryptoAI Master — 멀티팩터 스코어링 샘플 결과")
        print("=" * 70)

        for i, r in enumerate(results, 1):
            bar = "█" * int(r.total_score / 5) + "░" * (20 - int(r.total_score / 5))
            signal_emoji = {
                "STRONG_BUY": "🔥",
                "BUY": "🟢",
                "HOLD": "🟡",
                "SELL": "🔴",
            }
            emoji = signal_emoji.get(r.signal, "⚪")

            print(f"\n  #{i} [{r.symbol}]")
            print(f"  종합: {r.total_score:>6.1f}점  {bar}  {r.signal} {emoji}")
            print(f"  신뢰도: {r.confidence:.0f}%")
            print(f"  ├─ 기술분석: {r.technical_score:>5.1f}점")
            print(f"  ├─ 모멘텀:   {r.momentum_score:>5.1f}점")
            print(f"  ├─ 변동성:   {r.volatility_score:>5.1f}점")
            print(f"  ├─ 거래량:   {r.volume_score:>5.1f}점")
            print(f"  └─ 감성:     {r.sentiment_score:>5.1f}점")
            print(f"  💬 {r.reasoning}")

        print("\n" + "=" * 70)
        print(f"  매수 후보: {[r.symbol for r in results if r.signal in ('BUY','STRONG_BUY')]}")
        print("=" * 70)

        # Assertions
        assert len(results) == 4
        assert all(0 <= r.total_score <= 100 for r in results)
