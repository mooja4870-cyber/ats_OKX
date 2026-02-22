"""포지션(보유 중인 매수/숏 건) 추적"""

from __future__ import annotations

import json
from pathlib import Path
from loguru import logger
from src.utils.helpers import now_kst, format_usdt


class PositionTracker:
    """현재 보유 포지션 관리 (롱/숏 지원)"""

    def __init__(self):
        # pair → position dict
        self._positions: dict[str, dict] = {}
        self._state_path = Path("data/open_positions.json")
        self._load_positions()

    @staticmethod
    def _format_price(price: float) -> str:
        """저가 코인도 0으로 보이지 않게 가격 포맷"""
        if price >= 1000:
            return f"{price:,.2f}"
        if price >= 1:
            return f"{price:,.4f}"
        return f"{price:.6f}"

    def open_position(
        self,
        pair: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        trade_id: str,
        initial_margin: float,
        position_side: str = "long",
        market_type: str = "swap",
    ):
        """신규 포지션 등록"""
        now = now_kst().isoformat()
        self._positions[pair] = {
            "trade_id": trade_id,
            "pair": pair,
            "entry_price": entry_price,
            "quantity": quantity,
            "initial_quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "initial_margin": initial_margin,
            "position_side": position_side,  # "long" / "short"
            "market_type": market_type,      # "spot" / "swap"
            "entry_time": now,
            "peak_price": entry_price,       # 트레일링 스탑용 고점/저점
            "tp_stage_hit": 0,               # 0: None, 1: TP1 hit, 2: TP2 hit
            "trailing_active": False,        # TP1 이후 활성화
        }
        self._save_positions()

        side_emoji = "📥" if position_side == "long" else "📤"
        side_label = "LONG" if position_side == "long" else "SHORT"
        logger.info(
            f"[Position] {side_emoji} {side_label} 오픈 | {pair} | "
            f"Entry: {self._format_price(entry_price)} | Qty: {quantity:.6f} | "
            f"Margin: {initial_margin:.2f} USDT | "
            f"TP: {self._format_price(take_profit)} | "
            f"SL: {self._format_price(stop_loss)}"
        )

    def update_position(self, pair: str, updates: dict) -> bool:
        """포지션 정보 업데이트 (부분 청산 등)"""
        if pair in self._positions:
            self._positions[pair].update(updates)
            self._save_positions()
            return True
        return False

    def close_position(self, pair: str) -> dict | None:
        """포지션 청산 (반환 후 삭제)"""
        position = self._positions.pop(pair, None)
        if position:
            self._save_positions()
            side_label = position.get("position_side", "long").upper()
            logger.info(f"[Position] 🏁 {side_label} 종료 | {pair}")
        return position

    def get_position(self, pair: str) -> dict | None:
        """특정 페어 포지션 조회"""
        return self._positions.get(pair)

    def has_position(self, pair: str) -> bool:
        """포지션 보유 여부"""
        return pair in self._positions

    def get_all_positions(self) -> dict:
        """전체 포지션 조회"""
        return self._positions.copy()

    def get_unrealized_pnl(self, pair: str, current_price: float) -> dict | None:
        """미실현 손익 계산 (롱/숏 대응)"""
        pos = self._positions.get(pair)
        if not pos:
            return None

        entry = pos["entry_price"]
        qty = pos["quantity"]
        position_side = pos.get("position_side", "long")

        if position_side == "long":
            pnl_pct = (current_price - entry) / entry
            pnl_usdt = (current_price - entry) * qty
        else:  # short
            pnl_pct = (entry - current_price) / entry
            pnl_usdt = (entry - current_price) * qty

        return {
            "pair": pair,
            "position_side": position_side,
            "entry_price": entry,
            "current_price": current_price,
            "pnl_pct": pnl_pct,
            "pnl_usdt": pnl_usdt,
            "hold_time": pos["entry_time"],
        }

    def count(self) -> int:
        return len(self._positions)

    def _load_positions(self) -> None:
        """프로세스 재시작 시 기존 오픈 포지션 복구"""
        try:
            if not self._state_path.exists():
                return
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return

            restored: dict[str, dict] = {}
            for pair, pos in raw.items():
                if not isinstance(pos, dict):
                    continue
                try:
                    restored[str(pair)] = {
                        "trade_id": str(pos.get("trade_id", "")),
                        "pair": str(pos.get("pair", pair)),
                        "entry_price": float(pos.get("entry_price", 0.0)),
                        "quantity": float(pos.get("quantity", 0.0)),
                        "initial_quantity": float(pos.get("initial_quantity", pos.get("quantity", 0.0))),
                        "stop_loss": float(pos.get("stop_loss", 0.0)),
                        "take_profit": float(pos.get("take_profit", 0.0)),
                        "initial_margin": float(pos.get("initial_margin", 0.0)),
                        "position_side": str(pos.get("position_side", "long")),
                        "market_type": str(pos.get("market_type", "swap")),
                        "entry_time": str(
                            pos.get("entry_time", now_kst().isoformat())
                        ),
                        "peak_price": float(pos.get("peak_price", pos.get("entry_price", 0.0))),
                        "tp_stage_hit": int(pos.get("tp_stage_hit", 0)),
                        "trailing_active": bool(pos.get("trailing_active", False)),
                    }
                except (TypeError, ValueError):
                    continue

            self._positions = restored
            if restored:
                logger.info(
                    f"[Position] 🔁 오픈 포지션 복구 완료: {len(restored)}개"
                )
        except Exception as e:
            logger.warning(f"[Position] 포지션 복구 실패: {e}")

    def _save_positions(self) -> None:
        """오픈 포지션 저장"""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self._positions, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[Position] 포지션 저장 실패: {e}")
