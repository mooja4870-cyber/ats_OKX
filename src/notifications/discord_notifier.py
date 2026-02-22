"""디스코드 Webhook 알림 모듈 (OKX)"""

from __future__ import annotations

import aiohttp
import asyncio
from datetime import datetime
from loguru import logger
from src.utils.helpers import get_env, format_usdt, format_pct


class DiscordNotifier:
    """디스코드 Webhook 기반 알림 전송"""

    def __init__(self, config: dict):
        self.webhook_signal = self._validate_webhook(
            get_env("DISCORD_WEBHOOK_SIGNAL"), "DISCORD_WEBHOOK_SIGNAL"
        )
        self.webhook_report = self._validate_webhook(
            get_env("DISCORD_WEBHOOK_REPORT"), "DISCORD_WEBHOOK_REPORT"
        )
        self.webhook_error = self._validate_webhook(
            get_env("DISCORD_WEBHOOK_ERROR"), "DISCORD_WEBHOOK_ERROR"
        )
        self.webhook_system = self._validate_webhook(
            get_env("DISCORD_WEBHOOK_SYSTEM"), "DISCORD_WEBHOOK_SYSTEM"
        )
        self.colors = config["discord"]["embed_colors"]
        self._session: aiohttp.ClientSession | None = None

    @staticmethod
    def _validate_webhook(url: str, key: str) -> str:
        if (
            not url.startswith("https://discord.com/api/webhooks/")
            or "..." in url
        ):
            raise ValueError(f"{key} 값이 비어있거나 placeholder 입니다.")
        return url

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """내부 HTTP 세션 정리"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _send_webhook(self, webhook_url: str, embed: dict):
        """Webhook으로 Embed 메시지 전송"""
        payload = {"embeds": [embed]}
        try:
            session = await self._get_session()
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 204:
                    logger.debug("[Discord] 알림 전송 성공")
                elif resp.status == 429:
                    retry_after = (await resp.json()).get("retry_after", 1)
                    logger.warning(f"[Discord] Rate limit — {retry_after}s 대기")
                    await asyncio.sleep(retry_after)
                    await self._send_webhook(webhook_url, embed)
                else:
                    body = await resp.text()
                    logger.error(f"[Discord] 전송 실패 ({resp.status}): {body}")
        except Exception as e:
            logger.error(f"[Discord] 전송 예외: {e}")

    # ── 알림 유형별 메서드 ──

    async def notify_buy(self, trade_info: dict, signal_info: dict):
        """포지션 진입 알림 (롱/숏) — Discord.md 스타일"""
        pair = trade_info["pair"]
        price = trade_info["price"]
        qty = trade_info["quantity"]
        position_side = trade_info.get("position_side", "long")
        tp = signal_info.get("take_profit", 0)
        sl = signal_info.get("stop_loss", 0)
        leverage = signal_info.get("leverage", 10)
        
        side_emoji = "✅" if position_side == "long" else "❌"
        side_label = "롱" if position_side == "long" else "숏"
        color = self.colors["buy"]

        embed = {
            "title": f"📌 포지션 진입 | {pair}",
            "color": color,
            "description": (
                f"**━━━━━━━━━━━━━━━━━━━**\n"
                f"**{side_emoji} {side_label} 진입 | {pair} | {price:,.2f}**\n"
                f"   레버리지: {leverage}x | 수량: {qty:.6f}\n"
                f"   진입가: {price:,.2f} | 목표가: {tp:,.2f}\n"
                f"   손절가: {sl:,.2f}\n"
                f"   마진: {format_usdt(price * qty / leverage)}"
            ),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Mode: {trade_info.get('mode', 'paper')}"},
        }
        await self._send_webhook(self.webhook_signal, embed)

    async def notify_sell(
        self,
        trade_info: dict,
        entry_price: float,
        exit_reason: str,
        pnl_pct: float,
        pnl_usdt: float,
        hold_minutes: float,
    ):
        """포지션 청산 알림 — Discord.md 스타일"""
        pair = trade_info["pair"]
        exit_price = trade_info["price"]
        position_side = trade_info.get("position_side", "long")
        
        is_profit = pnl_pct >= 0
        emoji = "✅" if is_profit else "❌"
        side_label = "롱" if position_side == "long" else "숏"
        color = self.colors["sell_profit"] if is_profit else self.colors["sell_loss"]

        embed = {
            "title": f"📌 포지션 청산 | {pair}",
            "color": color,
            "description": (
                f"**━━━━━━━━━━━━━━━━━━━**\n"
                f"**{emoji} {side_label} 청산 | {pair} | {exit_price:,.2f}**\n"
                f"   진입가: {entry_price:,.2f} → 청산가: {exit_price:,.2f}\n"
                f"   **PnL: {pnl_usdt:+,.2f} USDT ({format_pct(pnl_pct * 100)})**\n"
                f"   보유시간: {int(hold_minutes // 60)}h {int(hold_minutes % 60)}m\n"
                f"   사유: {exit_reason}"
            ),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"Mode: {trade_info.get('mode', 'paper')}"},
        }
        await self._send_webhook(self.webhook_signal, embed)

    async def notify_liquidation_warning(self, pos_info: dict):
        """강제청산 임박 경고"""
        embed = {
            "title": "🚨 [긴급] 강제청산 임박",
            "color": self.colors["emergency"],
            "description": (
                f"**━━━━━━━━━━━━━━━━━━━**\n"
                f"**{pos_info['pair']} {pos_info['side'].upper()} | 청산가까지 {pos_info['dist']:.1f}% 남음**\n"
                f"현재가: {pos_info['current_price']:,.2f} | 청산가: {pos_info['liq_price']:,.2f}\n"
                f"마진비율: {pos_info['margin_ratio']:.1f}%"
            ),
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_error, embed)

    async def notify_position_report_1m(self, stats: dict):
        """1분 주기 잔고 스냅샷 리포트 — 사용자 상세 요청 스타일"""
        lines = [
            "💼 **잔고 스냅샷**",
            "**💰 총자산**",
            f"{stats['total_assets']:,.2f} USDT ({format_pct(stats['total_pnl_pct'] * 100)})",
            "",
            "**💵 현금**",
            f"{stats['cash_usdt']:,.2f} USDT",
            "",
            "**📦 평가총액**",
            f"{stats['eval_total_usdt']:,.2f} USDT ({stats['unrealized_pnl_usdt']:+,.2f} USDT, {format_pct(stats['unrealized_pnl_pct'])})",
            "",
            "**🧾 종목별 현황**"
        ]
        
        holdings = stats.get("holdings", [])
        if not holdings:
            lines.append("• 없음")
        else:
            for h in holdings:
                lines.append(f"• {h['symbol']}: 평가 {h['eval_usdt']:,.2f} USDT | 손익 {format_pct(h['pnl_pct'])}")
        
        lines.append(f"\nTime: {stats['time']}")

        embed = {
            "description": "\n".join(lines),
            "color": self.colors["system"],
        }
        await self._send_webhook(self.webhook_system, embed)

    async def notify_market_snapshot_5m(self, snapshot: dict):
        """5분 주기 시장 스냅샷"""
        lines = [
            "📈 [5분 시장 스냅샷]",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⏰ {snapshot['time']} KST\n",
            "📊 시장 현황"
        ]
        
        for k, v in snapshot['markets'].items():
            lines.append(f" {k}: {v['price']:,.2f} (5m: {v['chg_5m']:+.2f}% | 1h: {v['chg_1h']:+.2f}%)")
            
        lines.append("\n📉 전략 시그널")
        for k, v in snapshot['signals'].items():
            lines.append(f" {k}: RSI {v['rsi']:.1f} | {v['trend']} | {v['bb']}")
            
        embed = {
            "description": "\n".join(lines),
            "color": self.colors["system"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_system, embed)

    async def notify_performance_report_15m(self, stats: dict):
        """15분 성과 리포트"""
        lines = [
            "📊 [15분 성과 리포트]",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⏰ {stats['time']} KST\n",
            "♜ 세션 성과 (오늘)",
            f"  실현 PnL: {stats['realized_pnl']:+,.2f} USDT",
            f"  미실현 PnL: {stats['unrealized_pnl']:+,.2f} USDT",
            f"  거래 횟수: {stats['trades']}회 (승: {stats['wins']} | 패: {stats['losses']})",
            f"  승률: {stats['win_rate']:.1f}%\n",
            "📊 자산 현황",
            f"  총 자산: {stats['total_assets']:,.2f} USDT",
            f"  가용 잔고: {stats['free_balance']:,.2f} USDT",
            f"  마진 비율: {stats['margin_ratio']:.1f}%\n",
            "📉 드로다운",
            f"  오늘 최대 DD: {stats['max_dd']:.1f}%",
            f"  연속 손실: {stats['consec_losses']}회"
        ]
        
        embed = {
            "description": "\n".join(lines),
            "color": self.colors["system"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_system, embed)

    async def notify_hourly_report_1h(self, stats_pkg: dict):
        """1시간 주기 종합 리포트 — 사용자 상세 요청 스타일"""
        stats = stats_pkg["stats"]
        snap = stats_pkg["snapshot"]
        market = stats_pkg["market"]
        
        lines = [
            "📋 **[1시간 종합 리포트]**",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⏰ {stats_pkg['time']} KST\n",
            "═══ **거래 요약 (최근 1시간)** ═══",
            f" 총 거래: {stats['total_trades']}회",
            f" 실현 손익: {stats['total_pnl']:+,.2f} USDT",
            f" 수수료 합계: {stats['total_fees']:-.2f} USDT",
            f" 펀딩비 합계: {stats['total_funding']:-.2f} USDT",
            f" **순이익: {stats['net_pnl']:+,.2f} USDT**\n",
            "═══ **페어별 손익** ═══"
        ]
        
        pair_stats = stats.get("pair_stats", {})
        if not pair_stats:
            lines.append(" (거래 없음)")
        else:
            for pair, p_stat in pair_stats.items():
                emoji = " ⚠️" if p_stat["pnl"] < 0 else ""
                lines.append(f" {pair}: {p_stat['pnl']:+,.2f} ({p_stat['wins']}승 {p_stat['total'] - p_stat['wins']}패){emoji}")
        
        lines.append("\n═══ **전략 분석** ═══")
        side_stats = stats.get("side_stats", {})
        for side in ["long", "short"]:
            s_stat = side_stats.get(side, {"pnl": 0.0, "wins": 0, "total": 0})
            wr = (s_stat["wins"] / s_stat["total"] * 100) if s_stat["total"] > 0 else 0
            emoji = " ⚠️" if wr < 40 and s_stat["total"] > 0 else ""
            lines.append(f" {side.capitalize()} 성과: {s_stat['pnl']:+,.2f} ({s_stat['total']}거래, 승률 {wr:.0f}%){emoji}")
            
        lines.append(f" 평균 보유시간: {int(stats['avg_hold_minutes'])}분")
        bt = stats.get("best_trade", {})
        lines.append(f" 최대 단일 수익: {bt.get('pnl_usdt', 0):+,.2f} ({bt.get('pair', 'N/A')} {bt.get('position_side', '').upper()})")
        lines.append(f" Profit Factor: {stats['pf']:.2f}\n")
        
        lines.append("═══ **리스크 지표** ═══")
        lines.append(f" 최대 동시 포지션: {len(snap.get('holdings_items', []))}개")
        margin_usage = (snap.get("total_used_margin", 0) / snap.get("total_value_usdt", 1) * 100)
        lines.append(f" 현재 마진 사용률: {margin_usage:.1f}%\n")
        
        lines.append("═══ **시장 환경** ═══")
        lines.append(f" BTC 24h 변동률: {market['chg_24h']:+.2f}%")
        lines.append(f" 거래량 (vs 24h평균): {market.get('volume_ratio', 1.0):.1f}x")

        embed = {
            "description": "\n".join(lines),
            "color": self.colors["system"],
        }
        await self._send_webhook(self.webhook_report, embed)

    async def notify_daily_report(self, report: dict):
        """일일 종합 리포트 — 사용자 상세 요청 스타일"""
        lines = [
            "📊 **[일일 종합 리포트]**",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📅 {report['date']} | Day #{report.get('day_num', 1)}\n",
            "═══════ **💰 손익 요약** ═══════",
            f" 총 실현 PnL:    {report['total_pnl']:+,.2f} USDT",
            f" 수수료 합계:     {report['total_fees']:-.2f} USDT",
            f" 펀딩비 합계:     {report['total_funding']:-.2f} USDT",
            f" **순이익:         {report['net_pnl']:+,.2f} USDT ({report['net_pnl']/report['balance_start']*100:+.2f}%)**\n",
            "═══════ **📊 거래 통계** ═══════",
            f" 총 거래: {report['total_trades']}회",
            f" 승/패: {report['wins']}/{report['losses']} (승률 {report['win_rate']:.1f}%)",
            f" 평균 수익: {report['total_pnl']/report['total_trades'] if report['total_trades'] > 0 else 0:+,.2f} USDT",
            f" Profit Factor: {report.get('pf', 0):.2f}\n",
            "═══════ **🏆 Best & Worst** ═══════"
        ]
        
        bt = report.get("best_trade", {})
        wt = report.get("worst_trade", {})
        lines.append(f" 최고 수익: {bt.get('pnl_usdt', 0):+,.2f} {bt.get('pair', '')} {bt.get('position_side', '').upper()}")
        lines.append(f" 최고 손실: {wt.get('pnl_usdt', 0):+,.2f} {wt.get('pair', '')} {wt.get('position_side', '').upper()}")
        lines.append(f" 평균 보유: {int(report.get('avg_hold_minutes', 0))}m\n")
        
        lines.append("═══════ **💼 자산 변화** ═══════")
        lines.append(f" 시작 자산: {report['balance_start']:,.2f} USDT")
        lines.append(f" 종료 자산: {report['balance_end']:,.2f} USDT")
        change = report['balance_end'] - report['balance_start']
        lines.append(f" 변화: {change:+,.2f} ({change/report['balance_start']*100:+.2f}%)")
        lines.append(f" MDD (당일): {report.get('mdd', 0.0):.1f}%\n")
        
        lines.append("═══════ **📈 누적 성과** ═══════")
        lines.append(f" 운영 기간: {report.get('day_num', 1)}일")
        lines.append(" (누적 통계는 DB에서 점진적으로 확장 예정)")

        embed = {
            "description": "\n".join(lines),
            "color": self.colors["system"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_report, embed)

    async def notify_error(self, error_msg: str, severity: str = "ERROR"):
        """에러 알림"""
        embed = {
            "title": f"🔴 [시스템] {severity}",
            "description": f"```\n{error_msg}\n```",
            "color": self.colors["emergency"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_error, embed)

    async def notify_sync_warning(self, message: str):
        """포지션 불일치 경고"""
        embed = {
            "title": "⚠️ [위험] 포지션 불일치 감지",
            "description": message,
            "color": self.colors["emergency"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_error, embed)

    async def notify_unmanaged_position(self, pair: str, side: str, qty: float):
        """미관리 포지션 감지 알림"""
        embed = {
            "title": "⚠️ [주의] 미관리 포지션 감지",
            "description": (
                f"**거래소에는 있으나 봇 DB에 없는 포지션을 발견했습니다.**\n\n"
                f"• 종목: {pair}\n"
                f"• 방향: {side.upper()}\n"
                f"• 수량: {qty:.6f}\n\n"
                f"*이 포지션은 자동 청산되지 않으며 리포트에서 별도로 표시됩니다.*"
            ),
            "color": self.colors["emergency"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_error, embed)

    async def notify_system(self, title: str, message: str):
        """시스템 메시지"""
        embed = {
            "title": f"⚙️ [시스템] {title}",
            "description": message,
            "color": self.colors["system"],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_system, embed)

    async def notify_shutdown(self, stats: dict):
        """봇 종료 알림 — 사용자 요청 스타일"""
        from src.utils.helpers import now_kst
        now = now_kst()
        # "오늘 오전 10:44" 형식
        ampm = "오전" if now.hour < 12 else "오후"
        hour_12 = now.hour if now.hour <= 12 else now.hour - 12
        if hour_12 == 0: hour_12 = 12
        time_str = f"오늘 {ampm} {hour_12}:{now.minute:02d}"

        lines = [
            f"일일 거래: {stats['daily_trades']}회",
            f"일일 손익: {stats['daily_pnl_usdt']:+,.4f} USDT",
            f"최종 잔고: {stats['current_balance']:,.2f} USDT",
            time_str
        ]
        
        embed = {
            "title": "⚙️ [시스템] 봇 종료",
            "description": "\n".join(lines),
            "color": self.colors["system"],
        }
        await self._send_webhook(self.webhook_system, embed)

    async def notify_heartbeat(self, status: dict, uptime_str: str = ""):
        """생존 확인 리포트"""
        embed = {
            "title": "💓 [하트비트] 봇 생존 확인",
            "color": 0x2ecc71,
            "fields": [
                {"name": "상태", "value": "🟢 정상 운영중", "inline": True},
                {"name": "업타임", "value": uptime_str or "계산중", "inline": True},
                {"name": "총자산", "value": format_usdt(status.get("total_balance", 0)), "inline": True},
                {"name": "포지션", "value": f"{status.get('pos_count', 0)}개", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._send_webhook(self.webhook_system, embed)
