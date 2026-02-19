"""
CryptoAI Master — 주문 실행 관리자
===================================

업비트 거래소 API를 통한 실제 매수/매도 + 모의투자(Paper Trading).
모드 전환은 ``TRADING_MODE`` 환경변수로 제어합니다.

Usage:
    >>> mgr = OrderManager(db_manager=db, settings=settings)
    >>> mgr.execute_buy("BTC", amount=100_000, limit_price=143_000_000, score=93.2)
"""

from __future__ import annotations

import logging
import time
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlencode
from typing import Any, Dict, List, Optional, Protocol

import httpx
import jwt

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# 프로토콜 & 데이터 클래스
# ═══════════════════════════════════════════════════

class OrderDBProtocol(Protocol):
    """주문 관리에 필요한 DB 인터페이스."""

    def insert_trade_order(self, order: Dict[str, Any]) -> None: ...
    def upsert_position(self, position: Dict[str, Any]) -> None: ...
    def close_position(self, symbol: str) -> None: ...
    def get_open_positions(self) -> List[Dict[str, Any]]: ...
    def get_paper_balance(self) -> Dict[str, Any]: ...
    def update_paper_balance(self, delta_krw: float) -> None: ...


class SettingsProtocol(Protocol):
    """설정 인터페이스."""

    trading_mode: str          # "paper" | "live"
    upbit_api_key: str
    upbit_secret_key: str
    stop_loss_pct: float       # 예: -3.0
    take_profit_pct: float     # 예: 5.0
    total_budget: int
    budget_ratio: float


@dataclass
class OrderResult:
    """주문 실행 결과.

    Attributes:
        success: 주문 성공 여부.
        order_id: 거래소 주문 UUID 또는 모의투자 ID.
        symbol: 코인 심볼.
        side: "BUY" 또는 "SELL".
        order_type: "MARKET" 또는 "LIMIT".
        price: 체결 가격 (KRW).
        volume: 체결 수량.
        total_krw: 총 체결 금액 (KRW).
        fee: 수수료 (KRW).
        error: 실패 시 에러 메시지.
        timestamp: 체결 시각.
    """
    success: bool
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    order_type: str = ""
    price: float = 0.0
    volume: float = 0.0
    total_krw: float = 0.0
    fee: float = 0.0
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        if self.success:
            return (
                f"✅ {self.side} {self.symbol} | "
                f"{self.volume:.8f}개 × ₩{self.price:,.0f} = ₩{self.total_krw:,.0f}"
            )
        return f"❌ {self.side} {self.symbol} | 실패: {self.error}"


# ═══════════════════════════════════════════════════
# 메인 클래스
# ═══════════════════════════════════════════════════

class OrderManager:
    """주문 실행 관리자.

    업비트 API를 통한 실전 매매와 모의투자(Paper Trading)를 모두 지원합니다.
    ``TRADING_MODE`` 설정에 따라 자동 전환됩니다.

    Args:
        db_manager: DB 매니저 (OrderDBProtocol 구현체).
        settings: 앱 설정 (SettingsProtocol 구현체).

    Example:
        >>> mgr = OrderManager(db, settings)
        >>> result = mgr.execute_buy("BTC", 100_000, limit_price=143_000_000, score=93)
        >>> print(result)
        ✅ BUY BTC | 0.00069930개 × ₩143,000,000 = ₩100,000
    """

    # 업비트 최소 주문 금액 (KRW)
    MIN_ORDER_AMOUNT: float = 5_000.0

    # 업비트 거래 수수료율
    FEE_RATE: float = 0.0005  # 0.05%

    # API 호출 간 딜레이 (초) — 레이트 리밋 방지
    API_DELAY: float = 0.2

    def __init__(
        self,
        db_manager: OrderDBProtocol,
        settings: SettingsProtocol,
    ) -> None:
        self.db = db_manager
        self.settings = settings
        self.upbit: Optional[Any] = None

        if settings.trading_mode == "live":
            try:
                import pyupbit
                self.upbit = pyupbit.Upbit(
                    settings.upbit_api_key,
                    settings.upbit_secret_key,
                )
                logger.info("OrderManager 초기화 완료 | 모드=🔴 실전투자")
            except Exception as e:
                logger.error("업비트 API 초기화 실패: %s → 모의투자 전환", e)
                self.upbit = None
        else:
            logger.info("OrderManager 초기화 완료 | 모드=🧪 모의투자")

    # ─────────────────────────────────────────────
    # 매수
    # ─────────────────────────────────────────────

    def execute_buy(
        self,
        symbol: str,
        amount: float,
        order_type: str = "LIMIT",
        limit_price: Optional[float] = None,
        score: float = 0.0,
    ) -> OrderResult:
        """매수 주문을 실행합니다.

        Args:
            symbol: 코인 심볼 (예: "BTC").
            amount: 매수 금액 (KRW).
            order_type: "MARKET" 또는 "LIMIT".
            limit_price: 지정가 (LIMIT 주문 시 필수).
            score: 매수 당시 AI 스코어.

        Returns:
            OrderResult 객체.
        """
        market = f"KRW-{symbol}"

        # 유효성 검사
        if amount < self.MIN_ORDER_AMOUNT:
            error = f"최소 주문 금액 미달: ₩{amount:,.0f} < ₩{self.MIN_ORDER_AMOUNT:,.0f}"
            logger.warning("[매수 거부] %s | %s", symbol, error)
            return OrderResult(success=False, symbol=symbol, side="BUY", error=error)

        if order_type == "LIMIT" and not limit_price:
            error = "LIMIT 주문에는 limit_price가 필요합니다"
            logger.warning("[매수 거부] %s | %s", symbol, error)
            return OrderResult(success=False, symbol=symbol, side="BUY", error=error)

        logger.info(
            "[매수 시작] %s | ₩%s | %s | score=%.1f",
            symbol, f"{amount:,.0f}", order_type, score,
        )

        try:
            if self._is_paper_mode():
                result = self._paper_buy(symbol, market, amount, limit_price)
            else:
                result = self._live_buy(symbol, market, amount, order_type, limit_price)

            if result.success:
                # DB: 거래 기록 저장
                self.db.insert_trade_order({
                    "symbol": symbol,
                    "order_type": "BUY",
                    "order_method": order_type,
                    "price": result.price,
                    "volume": result.volume,
                    "total_krw": result.total_krw,
                    "status": "FILLED",
                    "trigger_reason": f"SCORE_{score:.0f}",
                    "score_at_trade": score,
                    "upbit_order_id": result.order_id,
                    "filled_at": result.timestamp,
                })

                # DB: 포지션 업데이트/생성
                self.db.upsert_position({
                    "symbol": symbol,
                    "avg_buy_price": result.price,
                    "volume": result.volume,
                    "current_price": result.price,
                    "pnl_pct": 0.0,
                    "pnl_krw": 0.0,
                    "status": "OPEN",
                    "opened_at": result.timestamp,
                })

                logger.info("[매수 완료] %s", result)

            return result

        except Exception as e:
            error_msg = f"주문 실행 오류: {e}"
            logger.error("[매수 실패] %s | %s", symbol, error_msg)

            # 실패 기록도 DB에 저장
            self._save_failed_order(symbol, "BUY", order_type, amount, error_msg)

            return OrderResult(
                success=False, symbol=symbol, side="BUY", error=error_msg
            )

    # ─────────────────────────────────────────────
    # 매도
    # ─────────────────────────────────────────────

    def execute_sell(
        self,
        symbol: str,
        volume: float,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        trigger_reason: str = "MANUAL",
    ) -> OrderResult:
        """매도 주문을 실행합니다.

        Args:
            symbol: 코인 심볼.
            volume: 매도 수량.
            order_type: "MARKET" (기본) 또는 "LIMIT".
            limit_price: 지정가 (LIMIT 주문 시).
            trigger_reason: 매도 사유 ("STOP_LOSS", "TAKE_PROFIT", "MANUAL").

        Returns:
            OrderResult 객체.
        """
        market = f"KRW-{symbol}"

        if volume <= 0:
            error = f"매도 수량 오류: {volume}"
            return OrderResult(success=False, symbol=symbol, side="SELL", error=error)

        logger.info(
            "[매도 시작] %s | 수량=%.8f | %s | 사유=%s",
            symbol, volume, order_type, trigger_reason,
        )

        try:
            if self._is_paper_mode():
                result = self._paper_sell(symbol, market, volume)
            else:
                result = self._live_sell(symbol, market, volume, order_type, limit_price)

            if result.success:
                # DB: 거래 기록
                self.db.insert_trade_order({
                    "symbol": symbol,
                    "order_type": "SELL",
                    "order_method": order_type,
                    "price": result.price,
                    "volume": result.volume,
                    "total_krw": result.total_krw,
                    "status": "FILLED",
                    "trigger_reason": trigger_reason,
                    "upbit_order_id": result.order_id,
                    "filled_at": result.timestamp,
                })

                # DB: 포지션 종료
                self.db.close_position(symbol)

                logger.info("[매도 완료] %s", result)

            return result

        except Exception as e:
            error_msg = f"매도 실행 오류: {e}"
            logger.error("[매도 실패] %s | %s", symbol, error_msg)
            self._save_failed_order(symbol, "SELL", order_type, 0, error_msg)
            return OrderResult(
                success=False, symbol=symbol, side="SELL", error=error_msg
            )

    # ─────────────────────────────────────────────
    # 잔고 조회
    # ─────────────────────────────────────────────

    def get_balance(self) -> Dict[str, Any]:
        """전체 잔고를 조회합니다.

        Returns:
            {
                "KRW": float,           # 원화 잔고
                "coins": {
                    "BTC": {"balance": float, "avg_buy_price": float},
                    ...
                }
            }
        """
        if self._is_paper_mode():
            return self.db.get_paper_balance()

        try:
            balances = self._upbit_private_request("GET", "/v1/accounts")
            result: Dict[str, Any] = {"KRW": 0.0, "coins": {}}

            if not isinstance(balances, list):
                logger.error("잔고 조회 실패: 응답이 리스트가 아님 → %s", type(balances))
                return result

            target_coins = {"BTC", "ETH", "XRP", "SOL"}

            for b in balances:
                currency = b.get("currency", "")
                balance_val = float(b.get("balance", 0))

                if currency == "KRW":
                    result["KRW"] = balance_val
                elif currency in target_coins and balance_val > 0:
                    result["coins"][currency] = {
                        "balance": balance_val,
                        "avg_buy_price": float(b.get("avg_buy_price", 0)),
                    }

            logger.debug("잔고 조회 완료 | KRW=₩%s", f"{result['KRW']:,.0f}")
            return result

        except Exception as e:
            logger.error("잔고 조회 실패: %s", e)
            return {"KRW": 0.0, "coins": {}}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """현재가를 조회합니다.

        Args:
            symbol: 코인 심볼.

        Returns:
            현재가 (KRW) 또는 None.
        """
        try:
            import pyupbit
            market = f"KRW-{symbol}"
            price = pyupbit.get_current_price(market)
            time.sleep(self.API_DELAY)
            return float(price) if price else None
        except Exception as e:
            logger.error("현재가 조회 실패 | %s | %s", symbol, e)
            return None

    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """복수 코인 현재가를 한 번에 조회합니다.

        Args:
            symbols: 코인 심볼 리스트.

        Returns:
            {symbol: price} 딕셔너리.
        """
        prices: Dict[str, float] = {}
        try:
            import pyupbit
            tickers = [f"KRW-{s}" for s in symbols]
            result = pyupbit.get_current_price(tickers)
            time.sleep(self.API_DELAY)

            if isinstance(result, dict):
                for ticker, price in result.items():
                    symbol = ticker.replace("KRW-", "")
                    if price:
                        prices[symbol] = float(price)
            elif isinstance(result, (int, float)):
                # 단일 코인 조회 시
                prices[symbols[0]] = float(result)

        except Exception as e:
            logger.error("복수 현재가 조회 실패: %s", e)

        return prices

    # ─────────────────────────────────────────────
    # 실전 투자 (Private)
    # ─────────────────────────────────────────────

    def _live_buy(
        self,
        symbol: str,
        market: str,
        amount: float,
        order_type: str,
        limit_price: Optional[float],
    ) -> OrderResult:
        """실전 매수 주문."""
        if not self.upbit:
            raise RuntimeError("업비트 API가 초기화되지 않았습니다.")

        time.sleep(self.API_DELAY)

        if order_type == "MARKET":
            resp = self.upbit.buy_market_order(market, amount)
        elif order_type == "LIMIT":
            volume = amount / limit_price
            resp = self.upbit.buy_limit_order(market, limit_price, volume)
        else:
            raise ValueError(f"지원하지 않는 주문 유형: {order_type}")

        if not resp or "error" in resp:
            error_detail = resp.get("error", {}) if resp else {}
            raise RuntimeError(
                f"업비트 API 오류: {error_detail.get('message', '알 수 없는 오류')}"
            )

        exec_price = float(resp.get("price", limit_price or 0))
        exec_volume = float(resp.get("volume", amount / exec_price if exec_price else 0))
        total = exec_price * exec_volume
        fee = total * self.FEE_RATE

        return OrderResult(
            success=True,
            order_id=resp.get("uuid", ""),
            symbol=symbol,
            side="BUY",
            order_type=order_type,
            price=exec_price,
            volume=exec_volume,
            total_krw=total,
            fee=fee,
        )

    def _live_sell(
        self,
        symbol: str,
        market: str,
        volume: float,
        order_type: str,
        limit_price: Optional[float],
    ) -> OrderResult:
        """실전 매도 주문."""
        if not self.upbit:
            raise RuntimeError("업비트 API가 초기화되지 않았습니다.")

        time.sleep(self.API_DELAY)

        if order_type == "MARKET":
            resp = self.upbit.sell_market_order(market, volume)
        elif order_type == "LIMIT" and limit_price:
            resp = self.upbit.sell_limit_order(market, limit_price, volume)
        else:
            raise ValueError(f"지원하지 않는 주문 유형: {order_type}")

        if not resp or "error" in resp:
            error_detail = resp.get("error", {}) if resp else {}
            raise RuntimeError(
                f"업비트 API 오류: {error_detail.get('message', '알 수 없는 오류')}"
            )

        exec_price = float(resp.get("price", limit_price or 0))
        total = exec_price * volume
        fee = total * self.FEE_RATE

        return OrderResult(
            success=True,
            order_id=resp.get("uuid", ""),
            symbol=symbol,
            side="SELL",
            order_type=order_type,
            price=exec_price,
            volume=volume,
            total_krw=total,
            fee=fee,
        )

    # ─────────────────────────────────────────────
    # 모의투자 (Paper Trading)
    # ─────────────────────────────────────────────

    def _paper_buy(
        self,
        symbol: str,
        market: str,
        amount: float,
        limit_price: Optional[float],
    ) -> OrderResult:
        """모의투자 매수. 실제 현재가를 조회하여 시뮬레이션합니다."""
        exec_price = limit_price or self.get_current_price(symbol)

        if not exec_price or exec_price <= 0:
            raise RuntimeError(f"현재가 조회 실패: {symbol}")

        volume = amount / exec_price
        fee = amount * self.FEE_RATE

        # 모의 잔고 차감
        self.db.update_paper_balance(-amount)

        logger.info(
            "[모의매수] %s | ₩%s → %.8f개 @ ₩%s",
            symbol, f"{amount:,.0f}", volume, f"{exec_price:,.0f}",
        )

        return OrderResult(
            success=True,
            order_id=f"paper_buy_{symbol}_{int(datetime.now().timestamp())}",
            symbol=symbol,
            side="BUY",
            order_type="MARKET",
            price=exec_price,
            volume=volume,
            total_krw=amount,
            fee=fee,
        )

    def _paper_sell(
        self,
        symbol: str,
        market: str,
        volume: float,
    ) -> OrderResult:
        """모의투자 매도."""
        exec_price = self.get_current_price(symbol)

        if not exec_price or exec_price <= 0:
            raise RuntimeError(f"현재가 조회 실패: {symbol}")

        total = volume * exec_price
        fee = total * self.FEE_RATE

        # 모의 잔고 가산
        self.db.update_paper_balance(total)

        logger.info(
            "[모의매도] %s | %.8f개 @ ₩%s = ₩%s",
            symbol, volume, f"{exec_price:,.0f}", f"{total:,.0f}",
        )

        return OrderResult(
            success=True,
            order_id=f"paper_sell_{symbol}_{int(datetime.now().timestamp())}",
            symbol=symbol,
            side="SELL",
            order_type="MARKET",
            price=exec_price,
            volume=volume,
            total_krw=total,
            fee=fee,
        )

    # ─────────────────────────────────────────────
    # 유틸리티
    # ─────────────────────────────────────────────

    def _is_paper_mode(self) -> bool:
        """모의투자 모드 여부."""
        return self.settings.trading_mode != "live" or self.upbit is None

    def _upbit_private_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """업비트 Private API 호출.

        pyupbit private 응답 파싱 이슈를 우회하기 위해 직접 JWT 요청을 사용합니다.
        """
        access_key = (self.settings.upbit_api_key or "").strip()
        secret_key = (self.settings.upbit_secret_key or "").strip()
        if not access_key or not secret_key:
            raise RuntimeError("업비트 API 키가 비어 있습니다")

        payload: Dict[str, Any] = {
            "access_key": access_key,
            "nonce": str(uuid.uuid4()),
        }
        if params:
            query_string = urlencode(params, doseq=True)
            payload["query_hash"] = hashlib.sha512(query_string.encode()).hexdigest()
            payload["query_hash_alg"] = "SHA512"

        token = jwt.encode(payload, secret_key, algorithm="HS256")
        if isinstance(token, bytes):
            token = token.decode()

        response = httpx.request(
            method=method.upper(),
            url=f"https://api.upbit.com{path}",
            params=params if params else None,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )

        body: Any
        try:
            body = response.json()
        except Exception:
            body = {"error": {"message": response.text or "응답 파싱 실패"}}

        if response.status_code >= 400:
            msg = "업비트 요청 실패"
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message") or err.get("name") or msg)
            raise RuntimeError(f"{msg} (HTTP {response.status_code})")

        return body

    def _save_failed_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        error: str,
    ) -> None:
        """실패한 주문을 DB에 기록합니다."""
        try:
            self.db.insert_trade_order({
                "symbol": symbol,
                "order_type": side,
                "order_method": order_type,
                "total_krw": amount,
                "status": "FAILED",
                "trigger_reason": f"ERROR: {error[:100]}",
            })
        except Exception:
            logger.exception("실패 주문 DB 저장도 실패")
