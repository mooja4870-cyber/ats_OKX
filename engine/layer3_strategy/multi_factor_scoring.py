"""
CryptoAI Master — 멀티팩터 스코어링 엔진
=========================================

30+ 기술지표를 5개 팩터로 분류하여 0-100점 종합 스코어를 산출합니다.

팩터 가중치 (기본값):
    - Technical  30%  (RSI, MACD, 볼린저밴드, 이동평균 등)
    - Momentum   25%  (가격 모멘텀, 스토캐스틱, ROC)
    - Volatility 15%  (ATR, 볼린저 폭, 변동성 레짐)
    - Volume     15%  (거래량 비율, OBV 추세)
    - Sentiment  15%  (공포탐욕지수, 역발상 전략)

시그널:
    - STRONG_BUY  (80점 이상)
    - BUY         (70점 이상)
    - HOLD        (31-69점)
    - SELL        (30점 이하)

Usage:
    >>> scorer = MultiFactorScoring(db_manager=db)
    >>> result = scorer.score_coin("BTC")
    >>> print(result.total_score, result.signal)
    93.2 STRONG_BUY
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# 프로토콜: DB 매니저 인터페이스
# ═══════════════════════════════════════════════════

class DBManagerProtocol(Protocol):
    """데이터베이스 매니저가 구현해야 할 인터페이스.

    실제 Supabase DBManager 또는 테스트용 Mock 모두 이 프로토콜을 따릅니다.
    """

    def get_latest_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """최신 기술지표 딕셔너리를 반환합니다."""
        ...

    def get_latest_volatility(self, symbol: str) -> Optional[Dict[str, Any]]:
        """최신 변동성 분석 결과를 반환합니다."""
        ...

    def get_latest_sentiment(self) -> Optional[Dict[str, Any]]:
        """최신 시장 감성 데이터를 반환합니다."""
        ...

    def insert_scoring_result(self, result: "ScoringResult") -> None:
        """스코어링 결과를 DB에 저장합니다."""
        ...


# ═══════════════════════════════════════════════════
# 데이터 클래스
# ═══════════════════════════════════════════════════

@dataclass
class FactorDetail:
    """개별 팩터의 세부 점수 내역.

    Attributes:
        name: 팩터 이름 (예: "RSI 과매도 시그널")
        raw_value: 원시 지표 값
        contribution: 이 항목이 팩터 점수에 기여한 점수 (+/-)
    """
    name: str
    raw_value: float
    contribution: float


@dataclass
class ScoringResult:
    """멀티팩터 스코어링 결과.

    Attributes:
        symbol: 코인 심볼 (BTC, ETH, XRP, SOL)
        technical_score: 기술적 분석 점수 (0-100)
        momentum_score: 모멘텀 점수 (0-100)
        volatility_score: 변동성 점수 (0-100)
        volume_score: 거래량 점수 (0-100)
        sentiment_score: 감성 점수 (0-100)
        total_score: 가중 평균 종합 점수 (0-100)
        signal: 매매 시그널 (STRONG_BUY, BUY, HOLD, SELL)
        confidence: 신뢰도 (0-100)
        reasoning: 한글 설명
        details: 팩터별 세부 내역
        timestamp: 스코어링 시각
    """
    symbol: str
    technical_score: float
    momentum_score: float
    volatility_score: float
    volume_score: float
    sentiment_score: float
    total_score: float
    signal: str
    confidence: float
    reasoning: str
    details: Dict[str, List[FactorDetail]] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화 가능한 딕셔너리로 변환합니다."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def __str__(self) -> str:
        bar = "█" * int(self.total_score / 5) + "░" * (20 - int(self.total_score / 5))
        return (
            f"[{self.symbol}] {self.total_score:.1f}점 {bar} "
            f"{self.signal} (신뢰도 {self.confidence:.0f}%)"
        )


# ═══════════════════════════════════════════════════
# 헬퍼: 스코어 클램핑
# ═══════════════════════════════════════════════════

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """값을 [lo, hi] 범위로 제한합니다."""
    return max(lo, min(hi, value))


# ═══════════════════════════════════════════════════
# 메인 클래스
# ═══════════════════════════════════════════════════

class MultiFactorScoring:
    """멀티팩터 스코어링 엔진.

    5개 팩터(기술·모멘텀·변동성·거래량·감성)를 가중 평균하여
    0-100점 종합 스코어와 매매 시그널을 산출합니다.

    Args:
        db_manager: DBManagerProtocol을 구현한 데이터베이스 매니저.
        weights: 팩터별 가중치 딕셔너리. 합계는 1.0이어야 합니다.
        buy_threshold: BUY 시그널 기준 점수 (기본 70).
        strong_buy_threshold: STRONG_BUY 기준 점수 (기본 80).
        sell_threshold: SELL 시그널 기준 점수 (기본 30).

    Example:
        >>> scorer = MultiFactorScoring(db_manager=db)
        >>> result = scorer.score_coin("BTC")
        >>> print(result)
        [BTC] 93.2점 ██████████████████░░ STRONG_BUY (신뢰도 87%)
    """

    DEFAULT_WEIGHTS: Dict[str, float] = {
        "technical": 0.30,
        "momentum": 0.25,
        "volatility": 0.15,
        "volume": 0.15,
        "sentiment": 0.15,
    }

    def __init__(
        self,
        db_manager: DBManagerProtocol,
        weights: Optional[Dict[str, float]] = None,
        buy_threshold: float = 70.0,
        strong_buy_threshold: float = 80.0,
        sell_threshold: float = 30.0,
    ) -> None:
        self.db = db_manager
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.buy_threshold = buy_threshold
        self.strong_buy_threshold = strong_buy_threshold
        self.sell_threshold = sell_threshold

        # 가중치 합계 검증
        total_weight = sum(self.weights.values())
        if not (0.99 <= total_weight <= 1.01):
            raise ValueError(
                f"가중치 합계가 1.0이 아닙니다: {total_weight:.4f}. "
                f"현재 가중치: {self.weights}"
            )

        logger.info(
            "MultiFactorScoring 초기화 | 가중치=%s | "
            "매수=%s | 강력매수=%s | 매도=%s",
            self.weights, self.buy_threshold,
            self.strong_buy_threshold, self.sell_threshold,
        )

    # ─────────────────────────────────────────────
    # 퍼블릭 API
    # ─────────────────────────────────────────────

    def score_coin(self, symbol: str) -> ScoringResult:
        """단일 코인을 스코어링합니다.

        Args:
            symbol: 코인 심볼 (예: "BTC", "ETH")

        Returns:
            ScoringResult 객체.

        Raises:
            ValueError: 지표 데이터가 없는 경우.
            RuntimeError: 스코어링 도중 예기치 않은 오류.
        """
        logger.info("스코어링 시작 | symbol=%s", symbol)

        try:
            # 1. 데이터 로드
            indicators = self.db.get_latest_indicators(symbol)
            volatility_data = self.db.get_latest_volatility(symbol)
            sentiment_data = self.db.get_latest_sentiment()

            if not indicators:
                raise ValueError(
                    f"[{symbol}] 기술지표 데이터가 없습니다. "
                    f"데이터 수집 파이프라인을 확인하세요."
                )

            # 2. 개별 팩터 점수 계산
            tech_score, tech_details = self._calc_technical_score(indicators)
            momentum_score, momentum_details = self._calc_momentum_score(indicators)
            vol_score, vol_details = self._calc_volatility_score(volatility_data)
            volume_score, volume_details = self._calc_volume_score(indicators)
            sent_score, sent_details = self._calc_sentiment_score(sentiment_data)

            # 3. 가중 평균 계산
            total_score = _clamp(
                self.weights["technical"] * tech_score
                + self.weights["momentum"] * momentum_score
                + self.weights["volatility"] * vol_score
                + self.weights["volume"] * volume_score
                + self.weights["sentiment"] * sent_score
            )

            # 4. 시그널 결정
            signal = self._determine_signal(total_score)

            # 5. 신뢰도 계산
            factor_scores = [tech_score, momentum_score, vol_score, volume_score, sent_score]
            confidence = self._calc_confidence(total_score, factor_scores)

            # 6. 한글 설명 생성
            reasoning = self._generate_reasoning(
                symbol, tech_score, momentum_score,
                vol_score, volume_score, sent_score, signal,
            )

            # 7. 세부 내역 조합
            details = {
                "technical": tech_details,
                "momentum": momentum_details,
                "volatility": vol_details,
                "volume": volume_details,
                "sentiment": sent_details,
            }

            # 8. 결과 객체 생성
            result = ScoringResult(
                symbol=symbol,
                technical_score=round(tech_score, 2),
                momentum_score=round(momentum_score, 2),
                volatility_score=round(vol_score, 2),
                volume_score=round(volume_score, 2),
                sentiment_score=round(sent_score, 2),
                total_score=round(total_score, 2),
                signal=signal,
                confidence=round(confidence, 2),
                reasoning=reasoning,
                details=details,
                timestamp=datetime.now(),
            )

            # 9. DB 저장
            try:
                self.db.insert_scoring_result(result)
                logger.info(
                    "스코어링 완료 | %s | score=%.1f | signal=%s | confidence=%.0f%%",
                    symbol, total_score, signal, confidence,
                )
            except Exception as db_err:
                logger.error(
                    "스코어링 DB 저장 실패 | %s | error=%s",
                    symbol, db_err,
                )
                # DB 저장 실패해도 결과는 반환

            return result

        except ValueError:
            raise
        except Exception as e:
            logger.exception("스코어링 실패 | symbol=%s", symbol)
            raise RuntimeError(
                f"[{symbol}] 스코어링 실패: {e}"
            ) from e

    def score_all_coins(self, coins: List[str]) -> List[ScoringResult]:
        """복수 코인을 스코어링하고 점수 내림차순 정렬합니다.

        Args:
            coins: 코인 심볼 리스트 (예: ["BTC", "ETH", "XRP", "SOL"])

        Returns:
            ScoringResult 리스트 (점수 내림차순).
        """
        logger.info("전체 코인 스코어링 시작 | coins=%s", coins)
        results: List[ScoringResult] = []

        for symbol in coins:
            try:
                result = self.score_coin(symbol)
                results.append(result)
            except (ValueError, RuntimeError) as e:
                logger.warning("코인 스코어링 스킵 | %s | %s", symbol, e)
                continue

        results.sort(key=lambda r: r.total_score, reverse=True)

        logger.info(
            "전체 코인 스코어링 완료 | %d/%d 성공 | 1위=%s(%.1f점)",
            len(results), len(coins),
            results[0].symbol if results else "없음",
            results[0].total_score if results else 0,
        )

        return results

    def get_buy_candidates(self, coins: List[str]) -> List[ScoringResult]:
        """매수 후보 코인만 필터링하여 반환합니다.

        Args:
            coins: 코인 심볼 리스트.

        Returns:
            BUY 또는 STRONG_BUY 시그널 코인만 포함된 리스트.
        """
        all_results = self.score_all_coins(coins)
        candidates = [
            r for r in all_results
            if r.signal in ("BUY", "STRONG_BUY")
        ]
        logger.info("매수 후보 %d개 / 전체 %d개", len(candidates), len(all_results))
        return candidates

    # ─────────────────────────────────────────────
    # 팩터 1: 기술적 분석 (Technical) — 30%
    # ─────────────────────────────────────────────

    def _calc_technical_score(
        self, ind: Dict[str, Any]
    ) -> tuple[float, List[FactorDetail]]:
        """기술적 분석 점수를 계산합니다.

        분석 지표:
            - RSI (14): 과매도/과매수 판별
            - MACD 히스토그램: 추세 전환 감지
            - 볼린저밴드 위치: 가격 밴드 내 상대 위치
            - 이동평균 배열: 5/20/60일 정배열·역배열
            - EMA 크로스: 단기·장기 EMA 교차
            - ADX: 추세 강도

        Args:
            ind: 기술지표 딕셔너리.

        Returns:
            (점수, 세부내역 리스트) 튜플.
        """
        score = 50.0
        details: List[FactorDetail] = []

        # ── RSI (14) ──
        rsi = ind.get("rsi_14", 50.0)
        rsi_contrib = 0.0
        if rsi < 20:
            rsi_contrib = 30.0      # 극도 과매도 — 강한 매수 시그널
        elif rsi < 30:
            rsi_contrib = 20.0      # 과매도
        elif rsi < 40:
            rsi_contrib = 10.0      # 약 과매도
        elif rsi > 85:
            rsi_contrib = -30.0     # 극도 과매수
        elif rsi > 75:
            rsi_contrib = -20.0     # 과매수
        elif rsi > 65:
            rsi_contrib = -5.0      # 약 과매수
        score += rsi_contrib
        details.append(FactorDetail("RSI(14)", round(rsi, 2), rsi_contrib))

        # ── MACD 히스토그램 ──
        macd_hist = ind.get("macd_histogram", 0.0)
        macd_signal = ind.get("macd_signal", 0.0)
        macd_contrib = 0.0
        if macd_hist > 0 and macd_signal < 0:
            macd_contrib = 15.0     # 양전환 (골든크로스)
        elif macd_hist > 0:
            macd_contrib = 8.0      # 양수 유지
        elif macd_hist < 0 and macd_signal > 0:
            macd_contrib = -12.0    # 음전환 (데드크로스)
        elif macd_hist < 0:
            macd_contrib = -5.0     # 음수 유지
        score += macd_contrib
        details.append(FactorDetail("MACD 히스토그램", round(macd_hist, 4), macd_contrib))

        # ── 볼린저밴드 위치 ──
        close = ind.get("current_price", 0.0)
        bb_lower = ind.get("bollinger_lower", 0.0)
        bb_upper = ind.get("bollinger_upper", 0.0)
        bb_contrib = 0.0
        if bb_upper > bb_lower > 0 and close > 0:
            bb_position = (close - bb_lower) / (bb_upper - bb_lower)
            if bb_position < 0.1:
                bb_contrib = 20.0    # 하단 이탈 근접
            elif bb_position < 0.25:
                bb_contrib = 12.0    # 하단 근접
            elif bb_position > 0.9:
                bb_contrib = -15.0   # 상단 이탈 근접
            elif bb_position > 0.75:
                bb_contrib = -8.0    # 상단 근접
            details.append(FactorDetail(
                "볼린저밴드 위치", round(bb_position, 3), bb_contrib
            ))
        else:
            details.append(FactorDetail("볼린저밴드 위치", 0.0, 0.0))
        score += bb_contrib

        # ── 이동평균 배열 (SMA 5/20/60) ──
        sma5 = ind.get("sma_5", 0.0)
        sma20 = ind.get("sma_20", 0.0)
        sma60 = ind.get("sma_60", 0.0)
        ma_contrib = 0.0
        if sma5 > 0 and sma20 > 0 and sma60 > 0:
            if sma5 > sma20 > sma60:
                ma_contrib = 12.0    # 완벽한 정배열
            elif sma5 > sma20:
                ma_contrib = 5.0     # 단기 강세
            elif sma5 < sma20 < sma60:
                ma_contrib = -12.0   # 역배열
            elif sma5 < sma20:
                ma_contrib = -5.0    # 단기 약세
        score += ma_contrib
        details.append(FactorDetail("이동평균 배열", 0.0, ma_contrib))

        # ── EMA 크로스 (12/26) ──
        ema12 = ind.get("ema_12", 0.0)
        ema26 = ind.get("ema_26", 0.0)
        ema_contrib = 0.0
        if ema12 > 0 and ema26 > 0:
            ema_diff_pct = (ema12 - ema26) / ema26 * 100
            if ema_diff_pct > 1.0:
                ema_contrib = 5.0
            elif ema_diff_pct < -1.0:
                ema_contrib = -5.0
        score += ema_contrib
        details.append(FactorDetail("EMA(12/26)", round(ema_contrib, 2), ema_contrib))

        # ── ADX (추세 강도) ──
        adx = ind.get("adx", 20.0)
        adx_contrib = 0.0
        if adx > 40:
            adx_contrib = 5.0       # 강한 추세 (방향 무관하게 가산)
        elif adx < 15:
            adx_contrib = -3.0      # 추세 없음 → 횡보
        score += adx_contrib
        details.append(FactorDetail("ADX", round(adx, 2), adx_contrib))

        return _clamp(score), details

    # ─────────────────────────────────────────────
    # 팩터 2: 모멘텀 (Momentum) — 25%
    # ─────────────────────────────────────────────

    def _calc_momentum_score(
        self, ind: Dict[str, Any]
    ) -> tuple[float, List[FactorDetail]]:
        """모멘텀 점수를 계산합니다.

        분석 지표:
            - 당일 가격 변동률 (이격도)
            - 스토캐스틱 K/D
            - ROC (Rate of Change)
            - CCI (Commodity Channel Index)

        Args:
            ind: 기술지표 딕셔너리.

        Returns:
            (점수, 세부내역 리스트) 튜플.
        """
        score = 50.0
        details: List[FactorDetail] = []

        # ── 가격 이격도 ──
        current = ind.get("current_price", 0.0)
        open_price = ind.get("open_price", current)
        gap_contrib = 0.0
        if open_price > 0:
            gap_pct = (current - open_price) / open_price * 100
            if -5 < gap_pct <= -3:
                gap_contrib = 15.0    # 적정 조정 (역발상 매수)
            elif -3 < gap_pct <= -0.5:
                gap_contrib = 20.0    # 소폭 조정
            elif -10 < gap_pct <= -5:
                gap_contrib = 5.0     # 큰 하락 (주의)
            elif gap_pct <= -10:
                gap_contrib = -15.0   # 급락 (위험)
            elif 0 < gap_pct <= 2:
                gap_contrib = 5.0     # 소폭 상승
            elif 2 < gap_pct <= 5:
                gap_contrib = -3.0    # 과열 주의
            elif gap_pct > 5:
                gap_contrib = -10.0   # 급등 후 조정 리스크
            details.append(FactorDetail(
                "가격 이격도", round(gap_pct, 2), gap_contrib
            ))
        score += gap_contrib

        # ── 스토캐스틱 K ──
        stoch_k = ind.get("stoch_k", 50.0)
        stoch_d = ind.get("stoch_d", 50.0)
        stoch_contrib = 0.0
        if stoch_k < 15:
            stoch_contrib = 20.0     # 극도 과매도
        elif stoch_k < 25:
            stoch_contrib = 12.0     # 과매도
        elif stoch_k > 85:
            stoch_contrib = -15.0    # 극도 과매수
        elif stoch_k > 75:
            stoch_contrib = -8.0     # 과매수
        # K/D 크로스
        if stoch_k > stoch_d and stoch_k < 30:
            stoch_contrib += 5.0     # 과매도 구간 골든크로스
        score += stoch_contrib
        details.append(FactorDetail("스토캐스틱 K", round(stoch_k, 2), stoch_contrib))

        # ── ROC (12기간) ──
        roc = ind.get("roc_12", 0.0)
        roc_contrib = 0.0
        if roc < -5:
            roc_contrib = 10.0       # 하락 후 반등 기대
        elif roc > 10:
            roc_contrib = -5.0       # 과열
        elif 0 < roc <= 5:
            roc_contrib = 5.0        # 완만한 상승
        score += roc_contrib
        details.append(FactorDetail("ROC(12)", round(roc, 2), roc_contrib))

        # ── CCI (20기간) ──
        cci = ind.get("cci_20", 0.0)
        cci_contrib = 0.0
        if cci < -200:
            cci_contrib = 15.0       # 극도 과매도
        elif cci < -100:
            cci_contrib = 8.0        # 과매도
        elif cci > 200:
            cci_contrib = -12.0      # 극도 과매수
        elif cci > 100:
            cci_contrib = -5.0       # 과매수
        score += cci_contrib
        details.append(FactorDetail("CCI(20)", round(cci, 2), cci_contrib))

        return _clamp(score), details

    # ─────────────────────────────────────────────
    # 팩터 3: 변동성 (Volatility) — 15%
    # ─────────────────────────────────────────────

    def _calc_volatility_score(
        self, vol: Optional[Dict[str, Any]]
    ) -> tuple[float, List[FactorDetail]]:
        """변동성 점수를 계산합니다.

        적정 변동성(MEDIUM)이 자동매매에 가장 유리합니다.
        LOW: 수익 기회 부족 / HIGH: 리스크 증가 / EXTREME: 위험

        Args:
            vol: 변동성 분석 딕셔너리 (None 허용).

        Returns:
            (점수, 세부내역 리스트) 튜플.
        """
        score = 50.0
        details: List[FactorDetail] = []

        if vol is None:
            details.append(FactorDetail("변동성 데이터", 0.0, 0.0))
            return score, details

        # ── 변동성 레짐 ──
        regime = vol.get("volatility_regime", "MEDIUM")
        regime_contrib = 0.0
        regime_map = {
            "LOW": -10.0,       # 횡보 — 수익 기회 부족
            "MEDIUM": 25.0,     # 적정 — 최적 환경
            "HIGH": 5.0,        # 높음 — 기회+리스크 공존
            "EXTREME": -20.0,   # 극단 — 위험
        }
        regime_contrib = regime_map.get(regime, 0.0)
        score += regime_contrib
        details.append(FactorDetail("변동성 레짐", 0.0, regime_contrib))

        # ── ATR 상대값 ──
        atr_pct = vol.get("atr_percent", 2.0)
        atr_contrib = 0.0
        if 1.0 <= atr_pct <= 3.0:
            atr_contrib = 10.0       # 적정 범위
        elif 3.0 < atr_pct <= 5.0:
            atr_contrib = 0.0        # 약간 높음
        elif atr_pct > 5.0:
            atr_contrib = -10.0      # 과도한 변동성
        elif atr_pct < 0.5:
            atr_contrib = -5.0       # 너무 낮음
        score += atr_contrib
        details.append(FactorDetail("ATR %", round(atr_pct, 2), atr_contrib))

        # ── 볼린저밴드 폭 ──
        bb_width = vol.get("bb_width", 0.0)
        bbw_contrib = 0.0
        if 0.02 < bb_width < 0.06:
            bbw_contrib = 5.0        # 적정 폭
        elif bb_width >= 0.10:
            bbw_contrib = -5.0       # 과도하게 넓음
        elif bb_width <= 0.01:
            bbw_contrib = -3.0       # 스퀴즈 (폭발 직전)
        score += bbw_contrib
        details.append(FactorDetail("볼린저 폭", round(bb_width, 4), bbw_contrib))

        return _clamp(score), details

    # ─────────────────────────────────────────────
    # 팩터 4: 거래량 (Volume) — 15%
    # ─────────────────────────────────────────────

    def _calc_volume_score(
        self, ind: Dict[str, Any]
    ) -> tuple[float, List[FactorDetail]]:
        """거래량 점수를 계산합니다.

        거래량 급증은 강한 시그널, 거래량 감소는 약한 시그널.

        Args:
            ind: 기술지표 딕셔너리.

        Returns:
            (점수, 세부내역 리스트) 튜플.
        """
        score = 50.0
        details: List[FactorDetail] = []

        # ── 거래량 비율 (현재 / 20일 평균) ──
        volume_ratio = ind.get("volume_ratio", 1.0)
        vr_contrib = 0.0
        if volume_ratio > 5.0:
            vr_contrib = 30.0        # 거래량 폭발 (5배 이상)
        elif volume_ratio > 3.0:
            vr_contrib = 22.0        # 매우 높음
        elif volume_ratio > 2.0:
            vr_contrib = 15.0        # 높음
        elif volume_ratio > 1.5:
            vr_contrib = 10.0        # 약간 높음
        elif volume_ratio > 1.0:
            vr_contrib = 3.0         # 평균 이상
        elif volume_ratio < 0.3:
            vr_contrib = -20.0       # 거래 급감
        elif volume_ratio < 0.5:
            vr_contrib = -12.0       # 거래 감소
        elif volume_ratio < 0.7:
            vr_contrib = -5.0        # 소폭 감소
        score += vr_contrib
        details.append(FactorDetail("거래량 비율", round(volume_ratio, 2), vr_contrib))

        # ── OBV 추세 ──
        obv_trend = ind.get("obv_trend", "NEUTRAL")
        obv_contrib = 0.0
        if obv_trend == "RISING":
            obv_contrib = 10.0       # 매집 감지
        elif obv_trend == "FALLING":
            obv_contrib = -8.0       # 이탈 감지
        score += obv_contrib
        details.append(FactorDetail("OBV 추세", 0.0, obv_contrib))

        # ── VWAP 대비 위치 ──
        vwap = ind.get("vwap", 0.0)
        close = ind.get("current_price", 0.0)
        vwap_contrib = 0.0
        if vwap > 0 and close > 0:
            vwap_pct = (close - vwap) / vwap * 100
            if vwap_pct < -2:
                vwap_contrib = 8.0   # VWAP 아래 (저평가)
            elif vwap_pct > 3:
                vwap_contrib = -5.0  # VWAP 위 (고평가)
            details.append(FactorDetail("VWAP 이격", round(vwap_pct, 2), vwap_contrib))
        score += vwap_contrib

        return _clamp(score), details

    # ─────────────────────────────────────────────
    # 팩터 5: 감성 (Sentiment) — 15%
    # ─────────────────────────────────────────────

    def _calc_sentiment_score(
        self, sentiment: Optional[Dict[str, Any]]
    ) -> tuple[float, List[FactorDetail]]:
        """감성(시장 심리) 점수를 계산합니다.

        역발상 전략: 극도의 공포 → 매수 / 극도의 탐욕 → 주의

        Args:
            sentiment: 감성 데이터 딕셔너리 (None 허용).

        Returns:
            (점수, 세부내역 리스트) 튜플.
        """
        score = 50.0
        details: List[FactorDetail] = []

        if sentiment is None:
            details.append(FactorDetail("감성 데이터", 0.0, 0.0))
            return score, details

        # ── 공포/탐욕 지수 (0-100) ──
        fear_greed = sentiment.get("fear_greed_index", 50)
        fg_contrib = 0.0
        if fear_greed < 15:
            fg_contrib = 30.0        # 극도의 공포 (역발상 강매수)
        elif fear_greed < 25:
            fg_contrib = 20.0        # 공포
        elif fear_greed < 35:
            fg_contrib = 10.0        # 약간의 공포
        elif fear_greed > 85:
            fg_contrib = -25.0       # 극도의 탐욕 (경고)
        elif fear_greed > 75:
            fg_contrib = -15.0       # 탐욕
        elif fear_greed > 65:
            fg_contrib = -8.0        # 약간의 탐욕
        score += fg_contrib
        details.append(FactorDetail("공포/탐욕 지수", fear_greed, fg_contrib))

        # ── 뉴스 감성 ──
        news_sentiment = sentiment.get("news_sentiment", 0.0)  # -1.0 ~ 1.0
        news_contrib = 0.0
        if news_sentiment > 0.5:
            news_contrib = 8.0
        elif news_sentiment > 0.2:
            news_contrib = 4.0
        elif news_sentiment < -0.5:
            news_contrib = -8.0
        elif news_sentiment < -0.2:
            news_contrib = -4.0
        score += news_contrib
        details.append(FactorDetail("뉴스 감성", round(news_sentiment, 2), news_contrib))

        # ── 소셜 미디어 언급량 ──
        social_volume = sentiment.get("social_volume_change", 0.0)
        social_contrib = 0.0
        if social_volume > 100:
            social_contrib = 5.0     # 언급 급증 (관심 증가)
        elif social_volume < -50:
            social_contrib = -3.0    # 관심 감소
        score += social_contrib
        details.append(FactorDetail("소셜 언급 변화율", round(social_volume, 1), social_contrib))

        return _clamp(score), details

    # ─────────────────────────────────────────────
    # 시그널 & 신뢰도
    # ─────────────────────────────────────────────

    def _determine_signal(self, total_score: float) -> str:
        """종합 점수에서 매매 시그널을 결정합니다.

        Args:
            total_score: 0-100 종합 점수.

        Returns:
            "STRONG_BUY", "BUY", "HOLD", 또는 "SELL".
        """
        if total_score >= self.strong_buy_threshold:
            return "STRONG_BUY"
        elif total_score >= self.buy_threshold:
            return "BUY"
        elif total_score <= self.sell_threshold:
            return "SELL"
        return "HOLD"

    def _calc_confidence(
        self, total_score: float, factor_scores: List[float]
    ) -> float:
        """신뢰도를 계산합니다.

        팩터 간 점수 일관성이 높을수록 신뢰도가 높습니다.
        극단적 점수(매우 높거나 낮은)일수록 기본 신뢰도가 높습니다.

        Args:
            total_score: 종합 점수.
            factor_scores: 5개 팩터 점수 리스트.

        Returns:
            0-100 신뢰도 값.
        """
        # 팩터 간 표준편차 (낮을수록 일관적)
        std_dev = float(np.std(factor_scores))
        consistency = max(0, 100 - std_dev * 2.5)

        # 기본 신뢰도 (극단 점수일수록 높음)
        distance_from_center = abs(total_score - 50)
        base_confidence = 40 + distance_from_center * 1.2

        # 팩터 중 BUY 시그널 동의 수
        buy_agreement = sum(1 for s in factor_scores if s >= 60)
        sell_agreement = sum(1 for s in factor_scores if s <= 40)
        agreement_bonus = max(buy_agreement, sell_agreement) * 5

        confidence = (base_confidence * 0.4 + consistency * 0.4 + agreement_bonus * 0.2)

        return _clamp(confidence)

    # ─────────────────────────────────────────────
    # 한글 설명 생성
    # ─────────────────────────────────────────────

    def _generate_reasoning(
        self,
        symbol: str,
        tech: float,
        momentum: float,
        vol: float,
        volume: float,
        sent: float,
        signal: str,
    ) -> str:
        """스코어링 결과에 대한 한글 설명을 생성합니다.

        Args:
            symbol: 코인 심볼.
            tech~sent: 각 팩터 점수.
            signal: 매매 시그널.

        Returns:
            사람이 읽기 쉬운 한글 설명 문자열.
        """
        factors = {
            "기술적 분석": tech,
            "모멘텀": momentum,
            "변동성": vol,
            "거래량": volume,
            "시장 심리": sent,
        }

        # 강점 (65점 이상)
        strengths = [
            name for name, score in factors.items() if score >= 65
        ]
        # 약점 (40점 이하)
        weaknesses = [
            name for name, score in factors.items() if score <= 40
        ]

        parts = [f"[{symbol}]"]

        # 시그널 설명
        signal_desc = {
            "STRONG_BUY": "강력 매수 추천 🔥",
            "BUY": "매수 추천 🟢",
            "HOLD": "관망 🟡",
            "SELL": "매도 추천 🔴",
        }
        parts.append(signal_desc.get(signal, "관망"))

        # 강점 설명
        if strengths:
            parts.append(f"강점: {', '.join(strengths)}")

        # 약점 설명
        if weaknesses:
            parts.append(f"주의: {', '.join(weaknesses)}")

        # 핵심 메시지
        if signal == "STRONG_BUY":
            parts.append("여러 팩터가 동시에 매수 시그널을 보내고 있습니다.")
        elif signal == "BUY":
            parts.append("전반적으로 긍정적이나 일부 주의 필요합니다.")
        elif signal == "SELL":
            parts.append("다수 팩터가 약세를 보이고 있어 매도를 권합니다.")
        else:
            parts.append("뚜렷한 방향성이 없어 관망을 권합니다.")

        return " | ".join(parts)
