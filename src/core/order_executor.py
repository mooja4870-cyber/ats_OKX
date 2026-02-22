"""주문 실행 모듈 (OKX 현물+선물)"""

from __future__ import annotations

import time
import json
import ccxt
from pathlib import Path
from loguru import logger
from src.utils.constants import (
    TradeMode,
    PositionSide,
    MarketType,
    OKX_MIN_ORDER_USDT,
    OKX_API_DELAY,
)
from src.utils.helpers import create_okx_exchange, now_kst, generate_trade_id


class OrderExecutor:
    """OKX 현물+선물 주문 실행기 (ccxt)"""

    def __init__(self, config: dict, exchange: ccxt.okx | None = None):
        self.mode = TradeMode(config["trading"]["mode"])
        self.fee_rate = config["risk"]["fee_rate"]
        self.market_type = config["trading"].get("market_type", "swap")  # spot / swap
        self.leverage = int(config["trading"].get("leverage", 1))
        self.margin_mode = config["trading"].get("margin_mode", "isolated")

        if self.mode in (TradeMode.LIVE, TradeMode.DEMO):
            if exchange is not None:
                self.exchange = exchange
            else:
                self.exchange = create_okx_exchange(self.mode.value)
            # 선물 레버리지 설정
            if self.market_type in ("swap", "both"):
                self._set_leverage_for_pairs(config)
            logger.info(f"🔴 [OrderExecutor] {self.mode.value.upper()} 모드 초기화 (OKX)")
        else:
            self.exchange = create_okx_exchange("paper")  # public API only
            self.exchange.timeout = 15000
            logger.info("🟡 [OrderExecutor] PAPER 모드 초기화 (OKX)")

        # 종이거래 가상 잔고
        self._paper_state_path = Path("data/paper_state.json")
        self._paper_balance_usdt = 10_000.0  # 10,000 USDT 가상
        self._paper_holdings: dict = {}  # {base_currency: quantity}
        self._price_cache: dict[str, float] = {}
        if self.mode == TradeMode.PAPER:
            self._load_paper_state()

    def _set_leverage_for_pairs(self, config: dict):
        """선물 모드 시 전체 페어 레버리지 설정"""
        pairs = config.get("trading", {}).get("pairs", [])
        for pair in pairs:
            if ":USDT" in pair:  # 선물 페어만
                try:
                    self.exchange.set_leverage(self.leverage, pair, params={
                        "mgnMode": self.margin_mode,
                    })
                    logger.info(
                        f"[OrderExecutor] 레버리지 설정: {pair} = {self.leverage}x "
                        f"({self.margin_mode})"
                    )
                except Exception as e:
                    logger.warning(f"[OrderExecutor] 레버리지 설정 실패 {pair}: {e}")

    # ═══════════════════════════════════════════
    #  공통 주문 인터페이스
    # ═══════════════════════════════════════════

    def open_long(self, pair: str, amount_usdt: float) -> dict | None:
        """
        롱 포지션 진입 (현물 매수 또는 선물 롱)

        Args:
            pair: 'BTC/USDT:USDT' (선물) 또는 'BTC/USDT' (현물)
            amount_usdt: 주문 금액 (USDT)
        """
        if amount_usdt < OKX_MIN_ORDER_USDT:
            logger.warning(
                f"[OrderExecutor] 최소 주문금액 미달: {amount_usdt:.2f} USDT"
            )
            return None

        trade_id = generate_trade_id(pair)

        if self.mode in (TradeMode.LIVE, TradeMode.DEMO):
            return self._live_open_long(pair, amount_usdt, trade_id)
        else:
            return self._paper_open_long(pair, amount_usdt, trade_id)

    def open_short(self, pair: str, amount_usdt: float) -> dict | None:
        """
        숏 포지션 진입 (선물 전용)

        Args:
            pair: 'BTC/USDT:USDT' (선물)
            amount_usdt: 주문 금액 (USDT)
        """
        if ":USDT" not in pair:
            logger.warning(f"[OrderExecutor] 숏은 선물 페어만 가능: {pair}")
            return None

        if amount_usdt < OKX_MIN_ORDER_USDT:
            logger.warning(
                f"[OrderExecutor] 최소 주문금액 미달: {amount_usdt:.2f} USDT"
            )
            return None

        trade_id = generate_trade_id(pair)

        if self.mode in (TradeMode.LIVE, TradeMode.DEMO):
            return self._live_open_short(pair, amount_usdt, trade_id)
        else:
            return self._paper_open_short(pair, amount_usdt, trade_id)

    def close_position(
        self, pair: str, quantity: float, position_side: str = "long"
    ) -> dict | None:
        """
        포지션 청산

        Args:
            pair: 심볼
            quantity: 청산 수량
            position_side: 'long' 또는 'short'
        """
        trade_id = generate_trade_id(pair)

        if self.mode in (TradeMode.LIVE, TradeMode.DEMO):
            return self._live_close(pair, quantity, position_side, trade_id)
        else:
            return self._paper_close(pair, quantity, position_side, trade_id)

    # 레거시 호환 (main.py에서 buy_market/sell_market 호출 대체)
    def buy_market(self, pair: str, amount_usdt: float) -> dict | None:
        return self.open_long(pair, amount_usdt)

    def sell_market(self, pair: str, quantity: float) -> dict | None:
        return self.close_position(pair, quantity, "long")

    def get_all_positions_standardized(self) -> list[dict]:
        """
        거래소(또는 Paper)의 모든 포지션을 표준 형식으로 변환하여 반환
        Returns:
            [{'pair': 'BTC/USDT:USDT', 'side': 'long', 'qty': 0.1}, ...]
        """
        results = []
        if self.mode in (TradeMode.LIVE, TradeMode.DEMO):
            try:
                positions = self.exchange.fetch_positions()
                for pos in positions:
                    contracts = float(pos.get("contracts", 0))
                    if contracts > 0:
                        results.append({
                            "pair": pos["symbol"],
                            "side": "long" if pos["side"] == "long" else "short",
                            "qty": contracts
                        })
            except Exception as e:
                logger.error(f"[OrderExecutor] 포지션 조회 실패: {e}")
        else:
            # Paper 모드
            state = self.get_paper_balance()
            holdings = state.get("holdings", {})
            for symbol_base, qty in holdings.items():
                if qty > 0:
                    pair = f"{symbol_base}/USDT:USDT" if "SHORT_" not in symbol_base else f"{symbol_base.replace('SHORT_', '')}/USDT:USDT"
                    side = "short" if "SHORT_" in symbol_base else "long"
                    results.append({
                        "pair": pair,
                        "side": side,
                        "qty": qty
                    })
        return results

    def cancel_all_orders(self, pair: str | None = None) -> bool:
        """모든 미체결 주문 취소"""
        if self.mode in (TradeMode.LIVE, TradeMode.DEMO):
            try:
                # pair가 지정되면 해당 페어만, 아니면 전체 (OKX는 보통 페어별 취소 권장)
                if pair:
                    self.exchange.cancel_all_orders(pair)
                else:
                    # 전체 페어에 대해 순회하며 취소 (config 기반)
                    # 여기서는 간단히 True 반환 (실제 필요시 구현)
                    pass
                return True
            except Exception as e:
                logger.error(f"[OrderExecutor] 주문 취소 실패: {e}")
                return False
        else:
            # Paper 모드는 미체결 주문 시스템이 없으므로 항상 성공
            return True

    # ═══════════════════════════════════════════
    #  현재가 조회
    # ═══════════════════════════════════════════

    def _safe_get_current_price(self, pair: str, retries: int = 2) -> float | None:
        """현재가 조회 (재시도 포함)"""
        for attempt in range(retries + 1):
            try:
                ticker = self.exchange.fetch_ticker(pair)
                price = float(ticker.get("last", 0))
                if price > 0:
                    self._price_cache[pair] = price
                    return price
            except Exception as e:
                if attempt == retries:
                    logger.warning(f"[OrderExecutor] 현재가 조회 실패: {pair} / {e}")
            time.sleep(OKX_API_DELAY * (attempt + 1))

        return self._price_cache.get(pair)

    @staticmethod
    def _format_price(price: float) -> str:
        """가격 표시 형식"""
        if price >= 1000:
            return f"{price:,.2f}"
        if price >= 1:
            return f"{price:,.4f}"
        return f"{price:.6f}"

    # ═══════════════════════════════════════════
    #  LIVE 주문 (OKX)
    # ═══════════════════════════════════════════

    def _live_open_long(
        self, pair: str, amount_usdt: float, trade_id: str
    ) -> dict | None:
        """LIVE 롱 진입"""
        try:
            price = self._safe_get_current_price(pair)
            if price is None or price <= 0:
                logger.error(f"[OrderExecutor] 가격 조회 실패: {pair}")
                return None

            quantity = amount_usdt / price

            is_swap = ":USDT" in pair
            params = {}
            if is_swap:
                params["tdMode"] = self.margin_mode
                params["posSide"] = "long"

            order = self.exchange.create_market_buy_order(pair, quantity, params=params)
            time.sleep(OKX_API_DELAY)

            filled_price = float(order.get("average", price))
            filled_qty = float(order.get("filled", quantity))
            cost = float(order.get("cost", filled_price * filled_qty))
            fee_info = order.get("fee", {})
            fee = abs(float(fee_info.get("cost", 0))) if fee_info else cost * self.fee_rate

            logger.info(
                f"[OrderExecutor] ✅ LIVE 롱 진입 | {pair} | "
                f"Price: {self._format_price(filled_price)} | Qty: {filled_qty:.6f}"
            )
            return {
                "trade_id": trade_id,
                "pair": pair,
                "side": "buy",
                "position_side": "long",
                "price": filled_price,
                "quantity": filled_qty,
                "amount_usdt": cost,
                "initial_margin": cost / self.leverage if self.leverage > 0 else cost,
                "fee_usdt": fee,
                "timestamp": now_kst().isoformat(),
                "mode": self.mode.value,
                "order_id": order.get("id"),
            }
        except Exception as e:
            logger.error(f"[OrderExecutor] LIVE 롱 진입 실패: {e}")
            return None

    def _live_open_short(
        self, pair: str, amount_usdt: float, trade_id: str
    ) -> dict | None:
        """LIVE 숏 진입"""
        try:
            price = self._safe_get_current_price(pair)
            if price is None or price <= 0:
                return None

            quantity = amount_usdt / price
            params = {
                "tdMode": self.margin_mode,
                "posSide": "short",
            }

            order = self.exchange.create_market_sell_order(pair, quantity, params=params)
            time.sleep(OKX_API_DELAY)

            filled_price = float(order.get("average", price))
            filled_qty = float(order.get("filled", quantity))
            cost = float(order.get("cost", filled_price * filled_qty))
            fee_info = order.get("fee", {})
            fee = abs(float(fee_info.get("cost", 0))) if fee_info else cost * self.fee_rate

            logger.info(
                f"[OrderExecutor] ✅ LIVE 숏 진입 | {pair} | "
                f"Price: {self._format_price(filled_price)} | Qty: {filled_qty:.6f}"
            )
            return {
                "trade_id": trade_id,
                "pair": pair,
                "side": "sell",
                "position_side": "short",
                "price": filled_price,
                "quantity": filled_qty,
                "amount_usdt": cost,
                "initial_margin": cost / self.leverage if self.leverage > 0 else cost,
                "fee_usdt": fee,
                "timestamp": now_kst().isoformat(),
                "mode": self.mode.value,
                "order_id": order.get("id"),
            }
        except Exception as e:
            logger.error(f"[OrderExecutor] LIVE 숏 진입 실패: {e}")
            return None

    def _live_close(
        self, pair: str, quantity: float, position_side: str, trade_id: str
    ) -> dict | None:
        """LIVE 포지션 청산"""
        try:
            is_swap = ":USDT" in pair
            params = {}
            if is_swap:
                params["tdMode"] = self.margin_mode
                params["posSide"] = position_side

            if position_side == "long":
                order = self.exchange.create_market_sell_order(pair, quantity, params=params)
            else:  # short
                order = self.exchange.create_market_buy_order(pair, quantity, params=params)

            time.sleep(OKX_API_DELAY)

            filled_price = float(order.get("average", 0))
            filled_qty = float(order.get("filled", quantity))
            cost = float(order.get("cost", filled_price * filled_qty))
            fee_info = order.get("fee", {})
            fee = abs(float(fee_info.get("cost", 0))) if fee_info else cost * self.fee_rate

            side_label = "롱 청산" if position_side == "long" else "숏 청산"
            logger.info(
                f"[OrderExecutor] ✅ LIVE {side_label} | {pair} | "
                f"Price: {self._format_price(filled_price)} | Qty: {filled_qty:.6f}"
            )
            return {
                "trade_id": trade_id,
                "pair": pair,
                "side": "sell" if position_side == "long" else "buy",
                "position_side": position_side,
                "price": filled_price,
                "quantity": filled_qty,
                "amount_usdt": cost,
                "fee_usdt": fee,
                "timestamp": now_kst().isoformat(),
                "mode": self.mode.value,
                "order_id": order.get("id"),
            }
        except Exception as e:
            logger.error(f"[OrderExecutor] LIVE 포지션 청산 실패: {e}")
            return None

    # ═══════════════════════════════════════════
    #  PAPER 주문
    # ═══════════════════════════════════════════

    def _paper_open_long(
        self, pair: str, amount_usdt: float, trade_id: str
    ) -> dict | None:
        """PAPER 롱 진입"""
        try:
            # 잔고 체크 시 사용 증거금을 기준으로 확인합니다.
            margin = amount_usdt / self.leverage if self.leverage > 0 else amount_usdt

            price = self._safe_get_current_price(pair)
            if price is None:
                return None

            fee = amount_usdt * self.fee_rate
            quantity = amount_usdt / price

            if margin + fee > self._paper_balance_usdt:
                logger.warning(
                    f"[OrderExecutor] PAPER 잔고 부족 | 필요 증거금+수수료: {margin+fee:.2f} USDT | "
                    f"지갑잔고: {self._paper_balance_usdt:.2f} USDT"
                )
                return None

            # 롱 진입 시 지갑잔고(Wallet Balance)에서는 수수료만 차감
            self._paper_balance_usdt -= fee
            
            base = pair.split("/")[0]
            self._paper_holdings[base] = self._paper_holdings.get(base, 0) + quantity
            self._save_paper_state()

            logger.info(
                f"[OrderExecutor] 📝 PAPER 롱 진입 | {pair} | "
                f"Price: {self._format_price(price)} | Qty: {quantity:.6f} | "
                f"잔고: {self._paper_balance_usdt:.2f} USDT"
            )

            return {
                "trade_id": trade_id,
                "pair": pair,
                "side": "buy",
                "position_side": "long",
                "price": price,
                "quantity": quantity,
                "amount_usdt": amount_usdt,
                "initial_margin": margin,
                "fee_usdt": fee,
                "timestamp": now_kst().isoformat(),
                "mode": "paper",
            }
        except Exception as e:
            logger.error(f"[OrderExecutor] PAPER 롱 진입 오류: {e}")
            return None

    def _paper_open_short(
        self, pair: str, amount_usdt: float, trade_id: str
    ) -> dict | None:
        """PAPER 숏 진입"""
        try:
            margin = amount_usdt / self.leverage if self.leverage > 0 else amount_usdt

            price = self._safe_get_current_price(pair)
            if price is None:
                return None

            fee = amount_usdt * self.fee_rate
            quantity = amount_usdt / price

            if margin + fee > self._paper_balance_usdt:
                logger.warning(
                    f"[OrderExecutor] PAPER 잔고 부족 | 필요 증거금+수수료: {margin+fee:.2f} USDT | "
                    f"지갑잔고: {self._paper_balance_usdt:.2f} USDT"
                )
                return None

            # 숏 진입 시 지갑잔고(Wallet Balance)에서는 수수료만 차감
            self._paper_balance_usdt -= fee

            short_key = f"SHORT_{pair.split('/')[0]}"
            self._paper_holdings[short_key] = (
                self._paper_holdings.get(short_key, 0) + quantity
            )
            self._save_paper_state()

            logger.info(
                f"[OrderExecutor] 📝 PAPER 숏 진입 | {pair} | "
                f"Price: {self._format_price(price)} | Qty: {quantity:.6f} | "
                f"잔고: {self._paper_balance_usdt:.2f} USDT"
            )

            return {
                "trade_id": trade_id,
                "pair": pair,
                "side": "sell",
                "position_side": "short",
                "price": price,
                "quantity": quantity,
                "amount_usdt": amount_usdt,
                "initial_margin": margin,
                "fee_usdt": fee,
                "timestamp": now_kst().isoformat(),
                "mode": "paper",
            }
        except Exception as e:
            logger.error(f"[OrderExecutor] PAPER 숏 진입 오류: {e}")
            return None

    def _paper_close(
        self, pair: str, quantity: float, position_side: str, trade_id: str
    ) -> dict | None:
        """PAPER 포지션 청산"""
        try:
            price = self._safe_get_current_price(pair)
            if price is None:
                return None

            amount_usdt = quantity * price
            fee = amount_usdt * self.fee_rate

            if position_side == "long":
                base = pair.split("/")[0]
                self._paper_holdings[base] = max(
                    0, self._paper_holdings.get(base, 0) - quantity
                )
            else:  # short
                short_key = f"SHORT_{pair.split('/')[0]}"
                self._paper_holdings[short_key] = max(
                    0, self._paper_holdings.get(short_key, 0) - quantity
                )

            # 종이거래 지갑잔고(Wallet Balance)에서는 수수료만 차감
            # 실현손익은 별도로 반영(add_paper_pnl)
            self._paper_balance_usdt -= fee

            self._save_paper_state()

            side_label = "롱 청산" if position_side == "long" else "숏 청산"
            logger.info(
                f"[OrderExecutor] 📝 PAPER {side_label} | {pair} | "
                f"Price: {self._format_price(price)} | Qty: {quantity:.6f} | "
                f"잔고: {self._paper_balance_usdt:.2f} USDT"
            )

            return {
                "trade_id": trade_id,
                "pair": pair,
                "side": "sell" if position_side == "long" else "buy",
                "position_side": position_side,
                "price": price,
                "quantity": quantity,
                "amount_usdt": amount_usdt,
                "fee_usdt": fee,
                "timestamp": now_kst().isoformat(),
                "mode": "paper",
            }
        except Exception as e:
            logger.error(f"[OrderExecutor] PAPER 포지션 청산 오류: {e}")
            return None

    # ═══════════════════════════════════════════
    #  Paper State 관리
    # ═══════════════════════════════════════════

    def add_paper_pnl(self, pnl_usdt: float) -> None:
        """종이거래 지갑 잔고에 실현손익 추가"""
        if self.mode == TradeMode.PAPER:
            self._paper_balance_usdt += pnl_usdt
            self._save_paper_state()
            logger.info(
                f"[OrderExecutor] 📝 PAPER 손익 합산 | PnL: {pnl_usdt:+.2f} USDT | 잔고: {self._paper_balance_usdt:.2f} USDT"
            )

    def get_paper_balance(self) -> dict:
        """종이거래 잔고 조회"""
        return {
            "usdt": self._paper_balance_usdt,
            "holdings": self._paper_holdings.copy(),
        }

    def _load_paper_state(self) -> None:
        """종이거래 상태(현금/보유수량) 복구"""
        try:
            if not self._paper_state_path.exists():
                return
            raw = json.loads(self._paper_state_path.read_text(encoding="utf-8"))
            usdt = float(raw.get("usdt", self._paper_balance_usdt))
            holdings_raw = raw.get("holdings", {})
            holdings: dict[str, float] = {}
            if isinstance(holdings_raw, dict):
                for currency, qty in holdings_raw.items():
                    try:
                        qty_f = float(qty)
                    except (TypeError, ValueError):
                        continue
                    if qty_f > 0:
                        holdings[str(currency)] = qty_f
            self._paper_balance_usdt = max(0.0, usdt)
            self._paper_holdings = holdings
            logger.info(
                "[OrderExecutor] PAPER 상태 복구 완료 | "
                f"잔고: {self._paper_balance_usdt:.2f} USDT | 종목수: {len(holdings)}"
            )
        except Exception as e:
            logger.warning(f"[OrderExecutor] PAPER 상태 복구 실패: {e}")

    def _save_paper_state(self) -> None:
        """종이거래 상태(현금/보유수량) 저장"""
        try:
            self._paper_state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "usdt": float(self._paper_balance_usdt),
                "holdings": {
                    k: float(v)
                    for k, v in self._paper_holdings.items()
                    if float(v) > 0
                },
            }
            self._paper_state_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[OrderExecutor] PAPER 상태 저장 실패: {e}")
