"""거래 기록 로거 (DB 저장 헬퍼) — OKX"""

from __future__ import annotations

import sqlite3
import json
from loguru import logger
from src.database.models import get_connection, close_connection


class TradeLogger:
    """거래 및 신호 기록 관리"""

    @staticmethod
    def _to_json_safe(value):
        """numpy 타입 등을 JSON 직렬화 가능한 기본 타입으로 변환"""
        if isinstance(value, dict):
            return {str(k): TradeLogger._to_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [TradeLogger._to_json_safe(v) for v in value]

        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        return str(value)

    @staticmethod
    def save_trade(trade: dict):
        """거래 기록 저장 (매수/매도 통합)"""
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
            INSERT OR REPLACE INTO trades (
                trade_id, pair, side, position_side, market_type,
                entry_price, exit_price, quantity,
                entry_time, exit_time, pnl_pct, pnl_usdt, fee_usdt,
                signal_score, exit_reason, trade_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.get("trade_id"),
                trade.get("pair"),
                trade.get("side"),
                trade.get("position_side", "long"),
                trade.get("market_type", "swap"),
                trade.get("entry_price"),
                trade.get("exit_price"),
                trade.get("quantity"),
                trade.get("entry_time"),
                trade.get("exit_time"),
                trade.get("pnl_pct"),
                trade.get("pnl_usdt"),
                trade.get("fee_usdt"),
                trade.get("signal_score"),
                trade.get("exit_reason"),
                trade.get("trade_mode"),
            ))
            conn.commit()
            logger.debug(f"[TradeLogger] ✅ 거래 저장 완료: {trade.get('trade_id')}")
        except sqlite3.IntegrityError:
            logger.warning(f"[TradeLogger] 중복 거래 ID: {trade.get('trade_id')}")
        except Exception as e:
            logger.error(f"[TradeLogger] 거래 저장 오류: {e}")
        finally:
            close_connection(conn)

    @staticmethod
    def save_signal(signal: dict):
        """신호 기록 저장"""
        conn = get_connection()
        cur = conn.cursor()

        try:
            conditions = TradeLogger._to_json_safe(signal.get("conditions", {}))
            acted = TradeLogger._to_json_safe(signal.get("acted"))

            cur.execute("""
            INSERT INTO signals (timestamp, pair, signal_type, score, conditions, acted, reason_skipped)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.get("timestamp"),
                signal.get("pair"),
                signal.get("signal_type"),
                signal.get("score"),
                json.dumps(conditions, ensure_ascii=False),
                int(bool(acted)),
                signal.get("reason_skipped"),
            ))
            conn.commit()
            logger.debug(
                f"[TradeLogger] 신호 기록: {signal.get('pair')} "
                f"{signal.get('signal_type')}"
            )
        except Exception as e:
            logger.error(f"[TradeLogger] 신호 저장 오류: {e}")
        finally:
            close_connection(conn)

    @staticmethod
    def save_daily_summary(date: str, summary: dict):
        """일일 요약 저장"""
        conn = get_connection()
        cur = conn.cursor()

        try:
            cur.execute("""
            INSERT OR REPLACE INTO daily_summary (
                date, total_trades, wins, losses, win_rate,
                total_pnl_usdt, max_drawdown_pct, balance_end
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                summary.get("total_trades", 0),
                summary.get("wins", 0),
                summary.get("losses", 0),
                summary.get("win_rate", 0.0),
                summary.get("total_pnl_usdt", 0.0),
                summary.get("max_drawdown_pct", 0.0),
                summary.get("balance_end", 0.0),
            ))
            conn.commit()
            logger.info(f"[TradeLogger] ✅ 일일 요약 저장: {date}")
        except Exception as e:
            logger.error(f"[TradeLogger] 일일 요약 저장 오류: {e}")
        finally:
            close_connection(conn)

    @staticmethod
    def get_trades_by_date(date: str) -> list[dict]:
        """특정 날짜 거래 조회"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        rows = cur.execute(
            "SELECT * FROM trades WHERE date(entry_time) = ? ORDER BY entry_time",
            (date,),
        ).fetchall()

        close_connection(conn)
        return [dict(row) for row in rows]

    @staticmethod
    def get_all_trades(limit: int = 100) -> list[dict]:
        """최근 거래 조회"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        rows = cur.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        close_connection(conn)
        return [dict(row) for row in rows]

    @staticmethod
    def get_daily_summary(date: str) -> dict | None:
        """특정 날짜 요약 조회"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        row = cur.execute(
            "SELECT * FROM daily_summary WHERE date = ?",
            (date,),
        ).fetchone()

        close_connection(conn)
        return dict(row) if row else None

    @staticmethod
    def calculate_daily_stats(date: str) -> dict:
        """특정 날짜 통계 계산 (보안됨)"""
        return TradeLogger.get_detailed_stats(start_time=f"{date} 00:00:00", end_time=f"{date} 23:59:59")

    @staticmethod
    def get_detailed_stats(start_time: str, end_time: str) -> dict:
        """기간별 상세 통계 계산"""
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 해당 기간에 종료된 거래들
        query = """
            SELECT * FROM trades 
            WHERE exit_time >= ? AND exit_time <= ? 
            ORDER BY exit_time ASC
        """
        rows = cur.execute(query, (start_time, end_time)).fetchall()
        trades = [dict(row) for row in rows]
        close_connection(conn)

        if not trades:
            return {
                "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "total_pnl": 0.0, "total_fees": 0.0, "net_pnl": 0.0,
                "pf": 0.0, "avg_hold_minutes": 0.0, "pairs": {}, "sides": {}
            }

        total_trades = len(trades)
        wins = 0
        losses = 0
        total_pnl = 0.0
        total_fees = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        
        pair_stats = {} # {pair: {"pnl": 0, "wins": 0, "total": 0}}
        side_stats = {"long": {"pnl": 0, "wins": 0, "total": 0}, "short": {"pnl": 0, "wins": 0, "total": 0}}
        
        total_hold_seconds = 0
        best_trade = trades[0]
        worst_trade = trades[0]

        from datetime import datetime
        for t in trades:
            pnl = t.get("pnl_usdt") or 0.0
            fee = t.get("fee_usdt") or 0.0
            total_pnl += pnl
            total_fees += fee
            
            # Profit Factor용
            if pnl > 0:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)
            
            # 베스트/워스트
            if pnl > best_trade["pnl_usdt"]: best_trade = t
            if pnl < worst_trade["pnl_usdt"]: worst_trade = t
            
            # 페어별
            p = t["pair"]
            if p not in pair_stats: pair_stats[p] = {"pnl": 0.0, "wins": 0, "total": 0}
            pair_stats[p]["pnl"] += pnl
            pair_stats[p]["total"] += 1
            if pnl > 0: pair_stats[p]["wins"] += 1
            
            # 사이드별
            side = t.get("position_side", "long")
            if side not in side_stats: side_stats[side] = {"pnl": 0.0, "wins": 0, "total": 0}
            side_stats[side]["pnl"] += pnl
            side_stats[side]["total"] += 1
            if pnl > 0: side_stats[side]["wins"] += 1
            
            # 보유 시간
            e_time = datetime.fromisoformat(t["entry_time"])
            x_time = datetime.fromisoformat(t["exit_time"])
            hold_sec = (x_time - e_time).total_seconds()
            total_hold_seconds += hold_sec

        net_pnl = total_pnl - total_fees
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        
        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / total_trades * 100),
            "total_pnl": total_pnl,
            "total_fees": total_fees,
            "total_funding": 0.0, # 펀딩비는 현재 추적 불가 -> 0
            "net_pnl": net_pnl,
            "pf": pf,
            "avg_hold_minutes": (total_hold_seconds / total_trades / 60) if total_trades > 0 else 0,
            "pair_stats": pair_stats,
            "side_stats": side_stats,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "trades_list": trades # 원본 리스트 (그래프용 등)
        }

    @staticmethod
    def delete_old_signals(days: int = 30):
        """오래된 신호 기록 삭제"""
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
        DELETE FROM signals WHERE created_at < datetime('now', '-{} days')
        """.format(days))

        deleted = cur.rowcount
        conn.commit()
        close_connection(conn)

        logger.info(f"[TradeLogger] 🗑️ {deleted}개 오래된 신호 삭제 (>{days}일)")
