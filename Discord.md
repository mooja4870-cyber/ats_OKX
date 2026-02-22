

# 디스코드 알림 항목 설계 (자동매매 봇 모니터링)

## 🔴 실시간 (즉시 알림) - Critical

```
⚡ [즉시 알림] 반드시 받아야 할 항목
```

### 1. 포지션 관련
```
📌 포지션 진입/청산
━━━━━━━━━━━━━━━━━━━
✅ 롱 진입 | BTC/USDT | 67,500.00
   레버리지: 10x | 수량: 0.05 BTC
   진입가: 67,500.00 | 청산가: 60,750.00
   마진: 337.50 USDT

❌ 숏 청산 | ETH/USDT | 3,450.00
   진입가: 3,500.00 → 청산가: 3,450.00
   PnL: +25.00 USDT (+1.43%)
   보유시간: 2h 34m
```

### 2. 리스크 경고
```
🚨 [긴급] 강제청산 임박
━━━━━━━━━━━━━━━━━━━
BTC/USDT LONG | 청산가까지 2.3% 남음
현재가: 62,100 | 청산가: 60,750
마진비율: 87.5%

⚠️ [경고] 대규모 미실현 손실
━━━━━━━━━━━━━━━━━━━
미실현 PnL: -450.00 USDT (-15.2%)
전체 자산 대비: -8.5%

🔥 [경고] 펀딩비 이상 감지
━━━━━━━━━━━━━━━━━━━
BTC 펀딩비: +0.15% (평소 대비 5배)
다음 정산: 12분 후
예상 비용: -7.50 USDT
```

### 3. 시스템 관련
```
🔴 [시스템] API 연결 끊김 | 재시도 3/5
🔴 [시스템] 주문 실패 | Insufficient margin
🔴 [시스템] 봇 비정상 종료
🟢 [시스템] 봇 재시작 완료
🔴 [시스템] Rate Limit 도달 (429)
```

### 4. 주문 관련
```
📋 주문 체결/실패
━━━━━━━━━━━━━━━━━━━
✅ Limit 주문 체결 | BTC LONG | 67,500
⚠️ 슬리피지 경고 | 예상: 67,500 → 실제: 67,535 (0.05%)
❌ 주문 실패 | 사유: Price exceeds limit
🔄 TP/SL 수정됨 | TP: 69,000 → 70,000
```

### 5. 시스템 및 초기화
```
⚙️ [초기화 완료]
━━━━━━━━━━━━━━━━━━━
• 기존 포지션 청산: 3건
• 미체결 주문 취소: 5건
• 내부 DB 리셋: 완료
• 잔고 스냅샷 리셋: 완료
• 시작 잔고: 10,000.00 USDT

⚠️ [미관리 포지션 감지 → 자동 청산]
━━━━━━━━━━━━━━━━━━━
• 티커: BTC/USDT:USDT
• 방향: LONG
• 수량: 0.05
• 사유: 봇 DB에 없는 포지션 관측됨
```

### 6. 교차 검증 (Sync Check)
```
⚠️ [포지션 증발 감지]
━━━━━━━━━━━━━━━━━━━
• 종목: ETH/USDT:USDT
• 방향: SHORT
• DB에는 존재하나 거래소에서 사라졌습니다. DB를 리셋합니다.
```

---

## 🟡 1분 주기 알림 - High Frequency

```
📊 [1분 리포트] 봇 관리 포지션 현황
━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ 2024-01-15 14:32:00 KST

📍 활성 포지션 (Managed Only)
┌─────────┬──────┬────────┬──────────┬─────────┐
│  페어    │ 방향 │ 레버리지│ 미실현PnL │ ROE%   │
├─────────┼──────┼────────┼──────────┼─────────┤
│ BTC/USDT│ LONG │  10x   │ +45.20   │ +4.52% │
│ ETH/USDT│ SHORT│   5x   │ -12.30   │ -1.23% │
└─────────┴──────┴────────┴──────────┴─────────┘

💰 총 미실현 PnL: +32.90 USDT
📈 마진 사용률: 45.2%
🎯 가장 가까운 TP/SL: BTC TP까지 1.2%
```

---

## 🟢 5분 주기 알림

```
📈 [5분 시장 스냅샷]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ 2024-01-15 14:35:00 KST

📊 시장 현황
 BTC: 67,520 (5m: +0.12% | 1h: -0.45%)
 ETH:  3,452 (5m: -0.08% | 1h: +0.22%)

📉 전략 시그널
 RSI(14): BTC 62.3 | ETH 45.1
 MACD: BTC 🟢매수 | ETH 🔴매도
 볼밴: BTC 상단근접 | ETH 중립

📋 대기 주문: 3개
 • BTC Limit Long @ 66,800 (현재가 대비 -1.1%)
 • ETH Limit Short @ 3,520 (현재가 대비 +2.0%)
 • BTC TP @ 69,000

🔍 변동성: BTC ATR(14) = 1,250 (높음)
```

---

## 🔵 15분 주기 알림

```
📊 [15분 성과 리포트]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ 2024-01-15 14:45:00 KST

💰 세션 성과 (오늘)
 실현 PnL: +125.40 USDT
 미실현 PnL: +32.90 USDT
 거래 횟수: 7회 (승: 5 | 패: 2)
 승률: 71.4%

📊 자산 현황
 총 자산: 10,158.30 USDT
 가용 잔고: 5,230.50 USDT
 사용 마진: 4,927.80 USDT
 마진 비율: 48.5%

📈 드로다운
 오늘 최대 DD: -3.2%
 연속 손실: 0회

🏦 펀딩비 현황
 BTC: +0.01% (4h 후 정산) 예상: -0.50 USDT
 ETH: -0.005% (4h 후 정산) 예상: +0.25 USDT
```

---

## ⚪ 1시간 주기 알림

```
📋 [1시간 종합 리포트]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ 2024-01-15 15:00:00 KST

═══ 거래 요약 (최근 1시간) ═══
 총 거래: 12회
 실현 손익: +89.50 USDT
 수수료 합계: -14.20 USDT
 펀딩비 합계: -3.50 USDT
 순이익: +71.80 USDT

═══ 페어별 손익 ═══
 BTC/USDT: +62.30 (5승 1패)
 ETH/USDT: +27.20 (3승 0패)
 SOL/USDT: -17.70 (0승 3패) ⚠️

═══ 전략 분석 ═══
 롱 성과: +95.20 (8거래, 승률 75%)
 숏 성과: -23.40 (4거래, 승률 25%) ⚠️
 평균 보유시간: 23분
 최대 단일 수익: +45.00 (BTC LONG)
 최대 단일 손실: -22.30 (SOL SHORT)
 Profit Factor: 2.14

═══ 리스크 지표 ═══
 Sharpe Ratio (1h): 1.85
 최대 동시 포지션: 3개
 최대 마진 사용률: 72.3%

═══ 시장 환경 ═══
 BTC 24h 변동률: +2.3%
 공포탐욕지수: 68 (탐욕)
 총 OI 변화: +$230M
 거래량 (vs 평균): 1.3x
```

---

## 🟣 일일 리포트 (24시간)

```
📊 [일일 종합 리포트]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 2024-01-15 | Day #45

═══════ 💰 손익 요약 ═══════
 총 실현 PnL:    +342.50 USDT
 수수료 합계:     -52.30 USDT
 펀딩비 합계:     -18.20 USDT
 순이익:         +272.00 USDT (+2.72%)

═══════ 📊 거래 통계 ═══════
 총 거래: 48회
 승/패: 31/17 (승률 64.6%)
 평균 수익: +18.50 USDT
 평균 손실: -8.30 USDT
 RR비율: 2.23:1
 Profit Factor: 2.41

═══════ 🏆 Best & Worst ═══════
 최고 수익: +89.00 BTC LONG 10x
 최고 손실: -45.00 SOL SHORT 5x
 최장 보유: 4h 22m (ETH LONG)
 최단 보유: 32s (BTC LONG) ⚠️

═══════ 💼 자산 변화 ═══════
 시작 자산: 9,886.30 USDT
 종료 자산: 10,158.30 USDT
 변화: +272.00 (+2.75%)
 ATH 대비: -1.2%
 MDD (당일): -4.8%

═══════ 📈 누적 성과 ═══════
 운영 기간: 45일
 누적 수익: +3,258.30 USDT
 초기 대비: +47.2%
 월 평균: +15.7%
 최대 DD: -12.3% (Day #23)

 📉 자산 그래프 (7일)
 ┌────────────────────────┐
 │         ╱╲    ╱        │ 10,200
 │    ╱╲╱╱    ╲╱          │ 10,000
 │╱╱╱                     │  9,800
 └────────────────────────┘
  Mon Tue Wed Thu Fri Sat Sun
```

---

## 🛠️ Python 구현 예시

```python
import discord
from discord import Webhook
import aiohttp
import asyncio
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import traceback


# ═══════════════════════════════════════
# 1. 설정 & 데이터 클래스
# ═══════════════════════════════════════

class AlertLevel(Enum):
    CRITICAL = "🔴"    # 즉시
    WARNING = "🟡"     # 즉시 (덜 긴급)
    INFO = "🟢"        # 주기적
    SYSTEM = "⚙️"      # 시스템


@dataclass
class DiscordConfig:
    # 채널별 웹훅 분리 (중요!)
    webhooks = {
        "critical":  "https://discord.com/api/webhooks/xxx/CRITICAL_CHANNEL",
        "trades":    "https://discord.com/api/webhooks/xxx/TRADES_CHANNEL",
        "report":    "https://discord.com/api/webhooks/xxx/REPORT_CHANNEL",
        "system":    "https://discord.com/api/webhooks/xxx/SYSTEM_CHANNEL",
        "heartbeat": "https://discord.com/api/webhooks/xxx/HEARTBEAT_CHANNEL",
    }
    mention_on_critical: str = "<@YOUR_USER_ID>"  # 긴급시 멘션
    mention_on_liquidation: str = "@everyone"


@dataclass
class Position:
    symbol: str
    side: str           # LONG / SHORT
    leverage: int
    entry_price: float
    current_price: float
    quantity: float
    margin: float
    liquidation_price: float
    unrealized_pnl: float
    roe_percent: float
    entry_time: datetime
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None


@dataclass
class TradeResult:
    symbol: str
    side: str
    leverage: int
    entry_price: float
    exit_price: float
    quantity: float
    realized_pnl: float
    pnl_percent: float
    hold_duration: str
    fees: float
    reason: str         # TP, SL, Signal, Manual


@dataclass
class BotStats:
    total_balance: float = 0.0
    available_balance: float = 0.0
    used_margin: float = 0.0
    margin_ratio: float = 0.0
    total_unrealized_pnl: float = 0.0
    daily_realized_pnl: float = 0.0
    daily_trades: int = 0
    daily_wins: int = 0
    daily_losses: int = 0
    max_drawdown: float = 0.0
    active_positions: list = field(default_factory=list)
    pending_orders: int = 0


# ═══════════════════════════════════════
# 2. 디스코드 알림 클래스
# ═══════════════════════════════════════

class DiscordNotifier:
    def __init__(self, config: DiscordConfig):
        self.config = config
        self._rate_limit_tracker = {}  # 중복 알림 방지

    async def _send(self, channel: str, embed: discord.Embed, 
                    content: str = None):
        """웹훅으로 메시지 전송"""
        url = self.config.webhooks[channel]
        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(url, session=session)
            try:
                await webhook.send(
                    content=content,
                    embed=embed,
                    username="Trading Bot 🤖"
                )
            except Exception as e:
                print(f"Discord send error: {e}")

    # ─── 즉시 알림: 포지션 진입 ───
    async def notify_position_open(self, pos: Position):
        emoji = "🟢" if pos.side == "LONG" else "🔴"
        color = 0x00ff00 if pos.side == "LONG" else 0xff0000

        embed = discord.Embed(
            title=f"{emoji} 포지션 진입 | {pos.symbol}",
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="포지션 정보",
            value=(
                f"```\n"
                f"방향:     {pos.side}\n"
                f"레버리지: {pos.leverage}x\n"
                f"진입가:   {pos.entry_price:,.2f}\n"
                f"수량:     {pos.quantity}\n"
                f"마진:     {pos.margin:,.2f} USDT\n"
                f"```"
            ),
            inline=False
        )
        embed.add_field(
            name="리스크 관리",
            value=(
                f"```\n"
                f"청산가: {pos.liquidation_price:,.2f}\n"
                f"TP:     {pos.tp_price:,.2f if pos.tp_price else 'N/A'}\n"
                f"SL:     {pos.sl_price:,.2f if pos.sl_price else 'N/A'}\n"
                f"청산까지: {abs(pos.current_price - pos.liquidation_price) / pos.current_price * 100:.1f}%\n"
                f"```"
            ),
            inline=False
        )

        await self._send("trades", embed)

    # ─── 즉시 알림: 포지션 청산 ───
    async def notify_position_close(self, trade: TradeResult):
        is_profit = trade.realized_pnl > 0
        emoji = "✅" if is_profit else "❌"
        color = 0x00ff00 if is_profit else 0xff0000

        embed = discord.Embed(
            title=f"{emoji} 포지션 청산 | {trade.symbol}",
            color=color,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="결과",
            value=(
                f"```diff\n"
                f"{'+ ' if is_profit else '- '}"
                f"{abs(trade.realized_pnl):,.2f} USDT "
                f"({trade.pnl_percent:+.2f}%)\n"
                f"```"
            ),
            inline=False
        )
        embed.add_field(
            name="상세",
            value=(
                f"```\n"
                f"방향:     {trade.side} {trade.leverage}x\n"
                f"진입:     {trade.entry_price:,.2f}\n"
                f"청산:     {trade.exit_price:,.2f}\n"
                f"수수료:   {trade.fees:,.2f} USDT\n"
                f"보유시간: {trade.hold_duration}\n"
                f"사유:     {trade.reason}\n"
                f"```"
            ),
            inline=False
        )

        await self._send("trades", embed)

    # ─── 즉시 알림: 긴급 경고 ───
    async def notify_liquidation_warning(self, pos: Position, 
                                          distance_pct: float):
        embed = discord.Embed(
            title="🚨 강제청산 임박 경고",
            color=0xff0000,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="위험 포지션",
            value=(
                f"```diff\n"
                f"- {pos.symbol} {pos.side} {pos.leverage}x\n"
                f"- 현재가:    {pos.current_price:,.2f}\n"
                f"- 청산가:    {pos.liquidation_price:,.2f}\n"
                f"- 남은거리:  {distance_pct:.2f}%\n"
                f"- 미실현PnL: {pos.unrealized_pnl:,.2f} USDT\n"
                f"```"
            ),
            inline=False
        )

        await self._send(
            "critical", embed,
            content=self.config.mention_on_liquidation
        )

    # ─── 즉시 알림: 시스템 에러 ───
    async def notify_system_error(self, error_type: str, 
                                   details: str, 
                                   retry_count: int = 0):
        embed = discord.Embed(
            title=f"🔴 시스템 오류: {error_type}",
            color=0xff0000,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="상세",
            value=f"```\n{details[:500]}\n```",
            inline=False
        )
        if retry_count > 0:
            embed.add_field(
                name="재시도", value=f"{retry_count}회", inline=True
            )

        await self._send(
            "system", embed,
            content=self.config.mention_on_critical
        )

    # ─── 1분 주기: 포지션 모니터링 ───
    async def notify_position_update(self, stats: BotStats):
        if not stats.active_positions:
            return  # 포지션 없으면 스킵

        embed = discord.Embed(
            title="📊 포지션 모니터링 (1분)",
            color=0x3498db,
            timestamp=datetime.utcnow()
        )

        pos_text = ""
        for p in stats.active_positions:
            emoji = "🟢" if p.unrealized_pnl >= 0 else "🔴"
            pos_text += (
                f"{emoji} **{p.symbol}** {p.side} {p.leverage}x\n"
                f"   PnL: `{p.unrealized_pnl:+,.2f}` "
                f"({p.roe_percent:+.2f}%)\n"
            )

        embed.add_field(
            name=f"활성 포지션 ({len(stats.active_positions)}개)",
            value=pos_text,
            inline=False
        )
        embed.add_field(
            name="총 미실현 PnL",
            value=f"`{stats.total_unrealized_pnl:+,.2f} USDT`",
            inline=True
        )
        embed.add_field(
            name="마진 사용률",
            value=f"`{stats.margin_ratio:.1f}%`",
            inline=True
        )

        await self._send("heartbeat", embed)

    # ─── 15분 주기: 성과 리포트 ───
    async def notify_performance_report(self, stats: BotStats):
        winrate = (
            (stats.daily_wins / stats.daily_trades * 100)
            if stats.daily_trades > 0 else 0
        )

        embed = discord.Embed(
            title="📈 15분 성과 리포트",
            color=0x9b59b6,
            timestamp=datetime.utcnow()
        )
        embed.add_field(
            name="💰 손익",
            value=(
                f"```\n"
                f"실현 PnL:   {stats.daily_realized_pnl:+,.2f} USDT\n"
                f"미실현 PnL: {stats.total_unrealized_pnl:+,.2f} USDT\n"
                f"```"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 거래",
            value=(
                f"거래: {stats.daily_trades}회\n"
                f"승률: {winrate:.1f}%\n"
                f"W/L: {stats.daily_wins}/{stats.daily_losses}"
            ),
            inline=True
        )
        embed.add_field(
            name="💼 자산",
            value=(
                f"총자산: {stats.total_balance:,.2f}\n"
                f"가용: {stats.available_balance:,.2f}\n"
                f"DD: {stats.max_drawdown:.1f}%"
            ),
            inline=True
        )

        await self._send("report", embed)

    # ─── 하트비트 (봇 생존 확인) ───
    async def notify_heartbeat(self, stats: BotStats, 
                                uptime: str):
        embed = discord.Embed(
            title="💓 봇 생존 확인",
            color=0x2ecc71,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="상태", value="🟢 정상 운영중", inline=True)
        embed.add_field(name="업타임", value=uptime, inline=True)
        embed.add_field(
            name="잔고", 
            value=f"{stats.total_balance:,.2f} USDT",
            inline=True
        )
        embed.add_field(
            name="포지션", 
            value=f"{len(stats.active_positions)}개",
            inline=True
        )

        await self._send("heartbeat", embed)


# ═══════════════════════════════════════
# 3. 스케줄러 통합
# ═══════════════════════════════════════

class MonitoringScheduler:
    """주기별 알림 스케줄러"""

    def __init__(self, notifier: DiscordNotifier, 
                 bot_engine):  # your trading bot
        self.notifier = notifier
        self.bot = bot_engine
        self.running = True

    async def run_all(self):
        """모든 모니터링 태스크 동시 실행"""
        await asyncio.gather(
            self.realtime_monitor(),    # 실시간
            self.one_min_monitor(),     # 1분
            self.five_min_monitor(),    # 5분
            self.fifteen_min_monitor(), # 15분
            self.hourly_monitor(),      # 1시간
            self.daily_monitor(),       # 24시간
            self.heartbeat_monitor(),   # 하트비트
        )

    async def realtime_monitor(self):
        """실시간 리스크 모니터링 (2초마다)"""
        while self.running:
            try:
                positions = self.bot.get_positions()
                for pos in positions:
                    # 청산 거리 계산
                    if pos.side == "LONG":
                        dist = ((pos.current_price - pos.liquidation_price) 
                                / pos.current_price * 100)
                    else:
                        dist = ((pos.liquidation_price - pos.current_price) 
                                / pos.current_price * 100)

                    # 청산 5% 이내 → 경고
                    if dist < 5.0:
                        await self.notifier.notify_liquidation_warning(
                            pos, dist
                        )

                    # 큰 손실 경고 (마진의 50% 이상)
                    if pos.unrealized_pnl < -(pos.margin * 0.5):
                        await self.notifier.notify_system_error(
                            "대규모 손실",
                            f"{pos.symbol} 미실현손실: "
                            f"{pos.unrealized_pnl:,.2f}"
                        )

            except Exception as e:
                await self.notifier.notify_system_error(
                    "모니터링 에러", traceback.format_exc()
                )
            
            await asyncio.sleep(2)

    async def one_min_monitor(self):
        """1분 포지션 업데이트"""
        while self.running:
            stats = self.bot.get_stats()
            await self.notifier.notify_position_update(stats)
            await asyncio.sleep(60)

    async def five_min_monitor(self):
        """5분 시장 스냅샷"""
        while self.running:
            # 시장 데이터 + 시그널 정보 전송
            await asyncio.sleep(300)

    async def fifteen_min_monitor(self):
        """15분 성과 리포트"""
        while self.running:
            stats = self.bot.get_stats()
            await self.notifier.notify_performance_report(stats)
            await asyncio.sleep(900)

    async def hourly_monitor(self):
        """1시간 종합 리포트"""
        while self.running:
            await asyncio.sleep(3600)

    async def daily_monitor(self):
        """일일 종합 리포트 (매일 09:00 KST)"""
        while self.running:
            await asyncio.sleep(60)
            now = datetime.now()
            if now.hour == 0 and now.minute == 0:  # UTC 00:00 = KST 09:00
                pass  # 일일 리포트 전송

    async def heartbeat_monitor(self):
        """5분마다 생존 확인"""
        while self.running:
            stats = self.bot.get_stats()
            uptime = self.bot.get_uptime()
            await self.notifier.notify_heartbeat(stats, uptime)
            await asyncio.sleep(300)
```

---

## 📋 채널 구성 권장

```
📁 Trading Bot
 ├── 🔴-critical        ← 청산경고, 시스템에러 (알림ON, 멘션)
 ├── 📊-trades          ← 진입/청산 기록
 ├── 📈-reports         ← 15분/1시간/일일 리포트
 ├── 💓-heartbeat       ← 1분 모니터링 + 생존확인
 └── ⚙️-system-logs     ← API에러, 재시작 등
```

## 핵심 정리

| 주기 | 항목 | 이유 |
|------|------|------|
| **즉시** | 진입/청산, 청산경고, 에러, 미관리 포지션 청산, 초기화 완료 | 돈과 직결된 핵심 이벤트 |
| **1분** | 봇 관리 포지션 PnL, 마진비율 | 실시간 리스크 트래킹 (Managed Only) |
| **5분** | 시장지표, 시그널, 대기주문 | 전략 보조 데이터 |
| **15분** | 세션성과, 승률, DD | 전략 건강도 체크 |
| **1시간** | 종합분석, 페어별/방향별 성과 | 전략 조정 근거 |
| **일일** | 누적성과, 자산곡선, 통계 | 장기 성과 측정 |

> **⚠️ 주의 (Sync Protocol)**: 봇이 직접 진입 신호를 보내지 않은 포지션은 즉시 자동 청산됩니다. 잔고 리포트는 오직 봇이 관리하는 포지션의 데이터만을 표시합니다.

> **레버리지 매매**에서 가장 중요한 건 **청산 임박 경고**와 **시스템 장애 알림**입니다. 이 두 개를 `@everyone` 멘션으로 절대 놓치지 않게 하세요.