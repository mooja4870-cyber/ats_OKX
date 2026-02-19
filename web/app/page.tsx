'use client';

/**
 * CryptoAI Master — 메인 대시보드 페이지
 */

import type { CSSProperties } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import {
  Bot,
  Activity,
  Shield,
  TrendingUp,
  Clock,
  Wifi,
  WifiOff,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AIRecommendationCards } from '@/components/dashboard/AIRecommendationCards';
import { GlassCard } from '@/components/ui/GlassCard';

interface PositionRow {
  symbol: string;
  volume: number;
  avg_buy_price: number;
  current_price: number;
  current_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
}

interface BalancePayload {
  total_krw?: number;
  total_value?: number;
  available_krw?: number;
  positions_value?: number;
}

interface TradeRecord {
  trade_id: string;
  symbol: string;
  side: 'BUY' | 'SELL' | string;
  amount: number;
  fee: number;
  pnl_krw?: number | null;
  timestamp: string;
}

interface AIAccuracyPayload {
  ai_accuracy?: number;
  ai_wins?: number;
  ai_closed_trades?: number;
}

type AccuracyRange = 'day' | 'week' | 'month';

interface AIAccuracyHistoryPoint {
  label: string;
  accuracy: number;
  wins: number;
  closed_trades: number;
}

interface AIAccuracyHistoryPayload {
  range?: AccuracyRange;
  accuracy?: number;
  wins?: number;
  closed_trades?: number;
  points?: AIAccuracyHistoryPoint[];
}

const formatKrw = (value: number | null) => {
  if (value === null) return '조회 중...';
  return `₩${Math.round(value).toLocaleString()}`;
};

export default function DashboardPage() {
  const [currentTime, setCurrentTime] = useState('');
  const [isOnline, setIsOnline] = useState(true);
  const [tradingMode, setTradingMode] = useState<'paper' | 'live' | 'unknown'>('unknown');

  const [totalAsset, setTotalAsset] = useState<number | null>(null);
  const [availableKrw, setAvailableKrw] = useState<number | null>(null);
  const [cashKrw, setCashKrw] = useState<number | null>(null);
  const [positionsValue, setPositionsValue] = useState<number | null>(null);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [aiAccuracy, setAiAccuracy] = useState<number | null>(null);
  const [aiWins, setAiWins] = useState<number>(0);
  const [aiClosedTrades, setAiClosedTrades] = useState<number>(0);
  const [tradeHistory, setTradeHistory] = useState<TradeRecord[]>([]);

  const [showAssetDetail, setShowAssetDetail] = useState(false);
  const [showTradeDetail, setShowTradeDetail] = useState(false);
  const [showRiskDetail, setShowRiskDetail] = useState(false);
  const [showAccuracyDetail, setShowAccuracyDetail] = useState(false);

  // 리스크 파라미터 (서버 설정)
  const [riskParams, setRiskParams] = useState<{
    stop_loss_pct: number;
    take_profit_pct: number;
    trailing_stop_pct: number;
    max_holding_hours: number;
    daily_loss_limit_pct: number;
  } | null>(null);
  const [aiRange, setAiRange] = useState<AccuracyRange>('day');
  const [aiHistoryAccuracy, setAiHistoryAccuracy] = useState<number | null>(null);
  const [aiHistoryWins, setAiHistoryWins] = useState<number>(0);
  const [aiHistoryClosedTrades, setAiHistoryClosedTrades] = useState<number>(0);
  const [aiHistoryPoints, setAiHistoryPoints] = useState<AIAccuracyHistoryPoint[]>([]);

  const totalUnrealizedPnl = useMemo(
    () => positions.reduce((acc, item) => acc + item.unrealized_pnl, 0),
    [positions],
  );

  const todayTrades = useMemo(() => {
    const now = new Date();
    return tradeHistory.filter((row) => {
      const parsed = new Date(row.timestamp);
      if (Number.isNaN(parsed.getTime())) return false;
      return (
        parsed.getFullYear() === now.getFullYear() &&
        parsed.getMonth() === now.getMonth() &&
        parsed.getDate() === now.getDate()
      );
    });
  }, [tradeHistory]);

  const todayRealizedPnl = useMemo(
    () => todayTrades.reduce((acc, row) => acc + (typeof row.pnl_krw === 'number' ? row.pnl_krw : 0), 0),
    [todayTrades],
  );

  const todayBuyAmount = useMemo(
    () => todayTrades.reduce((acc, row) => acc + (String(row.side).toUpperCase() === 'BUY' ? row.amount : 0), 0),
    [todayTrades],
  );

  const todaySellAmount = useMemo(
    () => todayTrades.reduce((acc, row) => acc + (String(row.side).toUpperCase() === 'SELL' ? row.amount : 0), 0),
    [todayTrades],
  );

  const todayTotalFee = useMemo(
    () => todayTrades.reduce((acc, row) => acc + (typeof row.fee === 'number' ? row.fee : 0), 0),
    [todayTrades],
  );

  const costBasis = useMemo(
    () => positions.reduce((acc, item) => acc + item.avg_buy_price * item.volume, 0),
    [positions],
  );

  const totalUnrealizedPnlPct = useMemo(() => {
    if (costBasis <= 0) return 0;
    return (totalUnrealizedPnl / costBasis) * 100;
  }, [costBasis, totalUnrealizedPnl]);

  // 리스크 레벨 동적 계산
  const riskLevel = useMemo(() => {
    if (positions.length === 0) return '안전';
    const stopLoss = riskParams?.stop_loss_pct ?? -3;
    const dangerCount = positions.filter((p) => p.unrealized_pnl_pct <= stopLoss).length;
    const warningCount = positions.filter(
      (p) => p.unrealized_pnl_pct > stopLoss && p.unrealized_pnl_pct <= stopLoss / 2,
    ).length;
    if (dangerCount > 0) return '높음';
    if (warningCount > 0) return '주의';
    return '낮음';
  }, [positions, riskParams]);

  // 실시간 시계
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setCurrentTime(
        now.toLocaleTimeString('ko-KR', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }),
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const tradingModeDotClass =
    tradingMode === 'live' ? 'bg-red-400' : tradingMode === 'paper' ? 'bg-yellow-400' : 'bg-slate-400';
  const tradingModeTextClass =
    tradingMode === 'live'
      ? 'text-red-400/80'
      : tradingMode === 'paper'
        ? 'text-yellow-400/80'
        : 'text-slate-300/80';
  const tradingModeLabel =
    tradingMode === 'live' ? '🔴 LIVE' : tradingMode === 'paper' ? '🧪 PAPER' : '⏳ CHECK';

  // 총 자산 + 포지션
  useEffect(() => {
    let cancelled = false;

    const loadAssetData = async () => {
      try {
        const [balanceResult, positionsResult] = await Promise.allSettled([
          fetch('/api/trades/balance', { cache: 'no-store' }),
          fetch('/api/trades/positions', { cache: 'no-store' }),
        ]);

        if (cancelled) return;

        if (balanceResult.status === 'fulfilled' && balanceResult.value.ok) {
          const payload = (await balanceResult.value.json()) as BalancePayload;
          setTotalAsset(typeof payload.total_value === 'number' ? payload.total_value : null);
          setAvailableKrw(typeof payload.available_krw === 'number' ? payload.available_krw : null);
          setCashKrw(typeof payload.total_krw === 'number' ? payload.total_krw : null);
          setPositionsValue(typeof payload.positions_value === 'number' ? payload.positions_value : null);
        }

        if (positionsResult.status === 'fulfilled' && positionsResult.value.ok) {
          const payload = (await positionsResult.value.json()) as PositionRow[];
          setPositions(Array.isArray(payload) ? payload : []);
        }
      } catch {
        // 네트워크 오류 시 기존 상태 유지
      }
    };

    loadAssetData();
    const id = setInterval(loadAssetData, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // 오늘 거래 이력 조회
  useEffect(() => {
    let cancelled = false;

    const loadTradeHistory = async () => {
      try {
        const res = await fetch('/api/trades/history?limit=100', { cache: 'no-store' });
        if (!res.ok) return;
        const payload = (await res.json()) as TradeRecord[];
        if (cancelled) return;
        setTradeHistory(Array.isArray(payload) ? payload : []);
      } catch {
        // 네트워크 오류 시 기존 값 유지
      }
    };

    loadTradeHistory();
    const id = setInterval(loadTradeHistory, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // AI 정확도(승률) 조회
  useEffect(() => {
    let cancelled = false;

    const loadAiAccuracy = async () => {
      try {
        const res = await fetch('/api/dashboard/ai-accuracy', { cache: 'no-store' });
        if (!res.ok) return;
        const payload = (await res.json()) as AIAccuracyPayload;
        if (cancelled) return;
        setAiAccuracy(typeof payload.ai_accuracy === 'number' ? payload.ai_accuracy : null);
        setAiWins(typeof payload.ai_wins === 'number' ? payload.ai_wins : 0);
        setAiClosedTrades(typeof payload.ai_closed_trades === 'number' ? payload.ai_closed_trades : 0);
      } catch {
        // 네트워크 오류 시 기존 값 유지
      }
    };

    loadAiAccuracy();
    const id = setInterval(loadAiAccuracy, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // AI 정확도 히스토리 조회 (패널 열림 시)
  useEffect(() => {
    if (!showAccuracyDetail) return;
    let cancelled = false;

    const loadAiHistory = async () => {
      try {
        const res = await fetch(`/api/dashboard/ai-accuracy/history?range=${aiRange}`, { cache: 'no-store' });
        if (!res.ok) return;
        const payload = (await res.json()) as AIAccuracyHistoryPayload;
        if (cancelled) return;
        setAiHistoryAccuracy(typeof payload.accuracy === 'number' ? payload.accuracy : null);
        setAiHistoryWins(typeof payload.wins === 'number' ? payload.wins : 0);
        setAiHistoryClosedTrades(typeof payload.closed_trades === 'number' ? payload.closed_trades : 0);
        setAiHistoryPoints(Array.isArray(payload.points) ? payload.points : []);
      } catch {
        // 네트워크 오류 시 기존 값 유지
      }
    };

    loadAiHistory();
    const id = setInterval(loadAiHistory, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [aiRange, showAccuracyDetail]);

  // 온라인 상태
  useEffect(() => {
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  // 서버 설정 기반 거래 모드 + 리스크 파라미터
  useEffect(() => {
    let cancelled = false;

    const loadConfig = async () => {
      try {
        const res = await fetch('/api/system/config', { cache: 'no-store' });
        if (!res.ok) return;
        const payload = (await res.json()) as {
          trading_mode?: string;
          risk_params?: {
            stop_loss_pct: number;
            take_profit_pct: number;
            trailing_stop_pct: number;
            max_holding_hours: number;
            daily_loss_limit_pct: number;
          };
        };
        if (cancelled) return;
        const mode = payload?.trading_mode?.toLowerCase() === 'live' ? 'live' : 'paper';
        setTradingMode(mode);
        if (payload?.risk_params) setRiskParams(payload.risk_params);
      } catch {
        // 네트워크 오류 시 기존 모드 유지
      }
    };

    loadConfig();
    const id = setInterval(loadConfig, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="min-h-screen grid-pattern">
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        {[...Array(3)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-[500px] h-[500px] rounded-full"
            style={{
              background: `radial-gradient(circle, ${['rgba(0,217,255,0.03)', 'rgba(182,32,224,0.03)', 'rgba(0,255,135,0.03)'][i]} 0%, transparent 70%)`,
              left: `${[10, 60, 40][i]}%`,
              top: `${[20, 50, 70][i]}%`,
            }}
            animate={{ x: [0, 30, -20, 0], y: [0, -20, 15, 0] }}
            transition={{ duration: 15 + i * 5, repeat: Infinity, ease: 'easeInOut' }}
          />
        ))}
      </div>

      <div
        className="relative z-10 max-w-[1440px] mx-auto space-y-8"
        style={{ padding: '33px 33px 48px 33px' }}
      >
        <motion.header
          className="space-y-4"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <motion.div
                className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-glow-cyan"
                whileHover={{ rotate: 12, scale: 1.1 }}
                transition={{ type: 'spring', stiffness: 300 }}
              >
                <Bot size={28} className="text-white" />
              </motion.div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold font-heading">
                  <span className="text-gradient-cyan">CryptoAI</span>
                  <span className="text-white/80 ml-2">Master</span>
                </h1>
                <p className="text-xs text-white/40 font-mono tracking-wider">
                  24H AUTONOMOUS AI TRADING SYSTEM
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <GlassCard className="px-3 py-1.5" hover={false}>
                <div className="flex items-center gap-2">
                  <Clock size={13} className="text-white/40" />
                  <span className="text-xs font-mono text-white/70 tabular-nums">{currentTime}</span>
                </div>
              </GlassCard>

              <GlassCard className="px-3 py-1.5" hover={false}>
                <div className="flex items-center gap-2">
                  {isOnline ? (
                    <Wifi size={13} className="text-green-400" />
                  ) : (
                    <WifiOff size={13} className="text-red-400" />
                  )}
                  <span className={`text-xs font-medium ${isOnline ? 'text-green-400/80' : 'text-red-400/80'}`}>
                    {isOnline ? 'LIVE' : 'OFFLINE'}
                  </span>
                </div>
              </GlassCard>

              <GlassCard className="px-3 py-1.5" hover={false}>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full animate-pulse ${tradingModeDotClass}`} />
                  <span className={`text-xs font-medium ${tradingModeTextClass}`}>
                    {tradingModeLabel}
                  </span>
                </div>
              </GlassCard>
            </div>
          </div>
        </motion.header>

        <motion.div
          className="grid grid-cols-2 sm:grid-cols-4 gap-3"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <StatusCard
            icon={<TrendingUp size={18} className="text-green-400" />}
            label="총 자산"
            value={formatKrw(totalAsset)}
            valueColorClass={
              totalUnrealizedPnl > 0
                ? 'text-red-400'
                : totalUnrealizedPnl < 0
                  ? 'text-blue-400'
                  : 'text-white'
            }
            sub="현금 + 평가액"
            subColor="text-cyan-300/90"
            actionLabel={showAssetDetail ? '닫기 ▲' : '상세 보기 ▼'}
            onClick={() => setShowAssetDetail((prev) => !prev)}
            active={showAssetDetail}
          />
          <StatusCard
            icon={<Activity size={18} className="text-cyan-400" />}
            label="오늘 거래"
            value={`${todayTrades.length}건`}
            sub={`${todayRealizedPnl >= 0 ? '+' : ''}₩${Math.round(todayRealizedPnl).toLocaleString()} 수익`}
            subColor="text-cyan-300/90"
            actionLabel={showTradeDetail ? '닫기 ▲' : '상세 보기 ▼'}
            onClick={() => setShowTradeDetail((prev) => !prev)}
            active={showTradeDetail}
          />
          <StatusCard
            icon={<Shield size={18} className="text-yellow-400" />}
            label="리스크"
            value={riskLevel}
            sub={`포지션 ${positions.length}개`}
            subColor="text-yellow-300/90"
            actionLabel={showRiskDetail ? '닫기 ▲' : '상세 보기 ▼'}
            onClick={() => setShowRiskDetail((prev) => !prev)}
            active={showRiskDetail}
          />
          <StatusCard
            icon={<Bot size={18} className="text-purple-400" />}
            label="AI 정확도"
            value={aiClosedTrades > 0 && aiAccuracy !== null ? `${aiAccuracy.toFixed(1)}%` : '—'}
            sub={aiClosedTrades > 0 ? `오늘 승 ${aiWins} / ${aiClosedTrades}건` : '오늘 거래 없음'}
            subColor="text-purple-300/90"
            actionLabel={showAccuracyDetail ? '닫기 ▲' : '상세 보기 ▼'}
            onClick={() => setShowAccuracyDetail((prev) => !prev)}
            active={showAccuracyDetail}
          />
        </motion.div>

        <AnimatePresence>
          {showAssetDetail && (
            <motion.section
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <GlassCard className="p-5 space-y-4" hover={false}>
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
                  <div>
                    <h3 className="text-base font-semibold text-white">총자산 상세</h3>
                    <p className="text-xs text-white/60">총자산 = 현금 + 평가액</p>
                  </div>
                  <div className="text-xs text-white/50">
                    주문 가능 현금: {formatKrw(availableKrw)}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <MetricCard label="현금" value={cashKrw} />
                  <MetricCard label="평가액" value={positionsValue} />
                  <MetricCard label="총자산" value={totalAsset} />
                  <MetricCard
                    label="평가손익"
                    value={totalUnrealizedPnl}
                    suffix={` (${totalUnrealizedPnl >= 0 ? '+' : ''}${totalUnrealizedPnlPct.toFixed(2)}%)`}
                    positive={totalUnrealizedPnl >= 0}
                    positiveColorClass="text-red-400"
                    negativeColorClass="text-blue-400"
                  />
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-white/60 border-b border-white/10">
                        <th className="text-left py-2 pr-4">종목</th>
                        <th className="text-right py-2 pr-4">수량</th>
                        <th className="text-right py-2 pr-4">매수가</th>
                        <th className="text-right py-2 pr-4">현재가</th>
                        <th className="text-right py-2 pr-4">손익금액(율)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-white/50">보유 종목이 없습니다.</td>
                        </tr>
                      ) : (
                        positions.map((row) => {
                          const positive = row.unrealized_pnl >= 0;
                          return (
                            <tr key={row.symbol} className="border-b border-white/5">
                              <td className="py-2 pr-4 text-white">{row.symbol}</td>
                              <td className="py-2 pr-4 text-right text-white/80">{row.volume.toFixed(8)}</td>
                              <td className="py-2 pr-4 text-right text-white/80">{`₩${Math.round(row.avg_buy_price).toLocaleString()}`}</td>
                              <td className="py-2 pr-4 text-right text-white/80">{`₩${Math.round(row.current_price).toLocaleString()}`}</td>
                              <td className={`py-2 pr-4 text-right font-medium ${positive ? 'text-red-400' : 'text-blue-400'}`}>
                                {`${positive ? '+' : ''}₩${Math.round(row.unrealized_pnl).toLocaleString()} (${row.unrealized_pnl_pct >= 0 ? '+' : ''}${row.unrealized_pnl_pct.toFixed(2)}%)`}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </GlassCard>
            </motion.section>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {showTradeDetail && (
            <motion.section
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <GlassCard className="p-5 space-y-4" hover={false}>
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
                  <div>
                    <h3 className="text-base font-semibold text-white">오늘 거래 상세</h3>
                    <p className="text-xs text-white/60">오늘 발생한 체결 이력과 수익 요약</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <HistoryMetricCard label="거래 건수" value={`${todayTrades.length}건`} />
                  <HistoryMetricCard label="총 매수" value={`₩${Math.round(todayBuyAmount).toLocaleString()}`} />
                  <HistoryMetricCard label="총 매도" value={`₩${Math.round(todaySellAmount).toLocaleString()}`} />
                  <HistoryMetricCard
                    label="총 수익"
                    value={`${todayRealizedPnl >= 0 ? '+' : ''}₩${Math.round(todayRealizedPnl).toLocaleString()}`}
                  />
                </div>

                <div className="text-xs text-white/50">
                  총 수수료: ₩{Math.round(todayTotalFee).toLocaleString()}
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-white/60 border-b border-white/10">
                        <th className="text-left py-2 pr-4">시간</th>
                        <th className="text-left py-2 pr-4">종목</th>
                        <th className="text-right py-2 pr-4">구분</th>
                        <th className="text-right py-2 pr-4">주문금액</th>
                        <th className="text-right py-2 pr-4">수수료</th>
                        <th className="text-right py-2 pr-4">손익</th>
                      </tr>
                    </thead>
                    <tbody>
                      {todayTrades.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-6 text-center text-white/50">
                            오늘 거래가 없습니다.
                          </td>
                        </tr>
                      ) : (
                        todayTrades.map((row) => {
                          const side = String(row.side).toUpperCase();
                          const pnl = typeof row.pnl_krw === 'number' ? row.pnl_krw : 0;
                          const positive = pnl >= 0;
                          const parsed = new Date(row.timestamp);
                          const timeText = Number.isNaN(parsed.getTime())
                            ? row.timestamp
                            : parsed.toLocaleTimeString('ko-KR', { hour12: false });
                          return (
                            <tr key={row.trade_id} className="border-b border-white/5">
                              <td className="py-2 pr-4 text-white/80">{timeText}</td>
                              <td className="py-2 pr-4 text-white">{row.symbol}</td>
                              <td className={`py-2 pr-4 text-right font-medium ${side === 'BUY' ? 'text-cyan-300' : 'text-rose-300'}`}>
                                {side}
                              </td>
                              <td className="py-2 pr-4 text-right text-white/80">
                                ₩{Math.round(row.amount).toLocaleString()}
                              </td>
                              <td className="py-2 pr-4 text-right text-white/60">
                                ₩{Math.round(row.fee ?? 0).toLocaleString()}
                              </td>
                              <td className={`py-2 pr-4 text-right font-medium ${positive ? 'text-green-400' : 'text-red-400'}`}>
                                {`${positive ? '+' : ''}₩${Math.round(pnl).toLocaleString()}`}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </GlassCard>
            </motion.section>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {showRiskDetail && (
            <motion.section
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <GlassCard className="p-5 space-y-4" hover={false}>
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
                  <div>
                    <h3 className="text-base font-semibold text-white">리스크 상세</h3>
                    <p className="text-xs text-white/60">포지션별 손익률과 리스크 기준값 비교</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {riskLevel === '높음' && (
                      <span className="flex items-center gap-1 text-xs text-red-400 font-semibold">
                        <XCircle size={14} /> 위험
                      </span>
                    )}
                    {riskLevel === '주의' && (
                      <span className="flex items-center gap-1 text-xs text-yellow-400 font-semibold">
                        <AlertTriangle size={14} /> 주의
                      </span>
                    )}
                    {(riskLevel === '낮음' || riskLevel === '안전') && (
                      <span className="flex items-center gap-1 text-xs text-green-400 font-semibold">
                        <CheckCircle2 size={14} /> 안전
                      </span>
                    )}
                  </div>
                </div>

                {/* 리스크 파라미터 */}
                {riskParams && (
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
                      <div className="text-[10px] text-white/50">손절 기준</div>
                      <div className="text-sm font-mono font-semibold text-red-400">
                        {riskParams.stop_loss_pct}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
                      <div className="text-[10px] text-white/50">익절 기준</div>
                      <div className="text-sm font-mono font-semibold text-green-400">
                        +{riskParams.take_profit_pct}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
                      <div className="text-[10px] text-white/50">트레일링 스탑</div>
                      <div className="text-sm font-mono font-semibold text-yellow-400">
                        {riskParams.trailing_stop_pct}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
                      <div className="text-[10px] text-white/50">최대 보유</div>
                      <div className="text-sm font-mono font-semibold text-cyan-300">
                        {riskParams.max_holding_hours}h
                      </div>
                    </div>
                    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
                      <div className="text-[10px] text-white/50">일일 최대 손실</div>
                      <div className="text-sm font-mono font-semibold text-red-400">
                        {riskParams.daily_loss_limit_pct}%
                      </div>
                    </div>
                  </div>
                )}

                {/* 포지션별 리스크 게이지 */}
                {positions.length === 0 ? (
                  <div className="py-6 text-center text-white/50 text-sm">보유 포지션이 없습니다.</div>
                ) : (
                  <div className="space-y-3">
                    {positions.map((row) => {
                      const stopLoss = riskParams?.stop_loss_pct ?? -3;
                      const takeProfit = riskParams?.take_profit_pct ?? 5;
                      const pnlPct = row.unrealized_pnl_pct;
                      // 게이지: 손절~익절 범위를 0~100%로 매핑
                      const range = takeProfit - stopLoss;
                      const gaugeRaw = ((pnlPct - stopLoss) / range) * 100;
                      const gauge = Math.max(0, Math.min(100, gaugeRaw));
                      const barColor =
                        pnlPct <= stopLoss
                          ? 'bg-red-500'
                          : pnlPct <= stopLoss / 2
                            ? 'bg-yellow-500'
                            : pnlPct >= takeProfit * 0.8
                              ? 'bg-green-400'
                              : 'bg-cyan-400';
                      const statusIcon =
                        pnlPct <= stopLoss ? (
                          <XCircle size={14} className="text-red-400" />
                        ) : pnlPct <= stopLoss / 2 ? (
                          <AlertTriangle size={14} className="text-yellow-400" />
                        ) : (
                          <CheckCircle2 size={14} className="text-green-400" />
                        );

                      return (
                        <div key={row.symbol} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              {statusIcon}
                              <span className="text-sm font-semibold text-white">{row.symbol}</span>
                              <span className="text-xs text-white/40">
                                매수가 ₩{Math.round(row.avg_buy_price).toLocaleString()}
                              </span>
                            </div>
                            <span
                              className={`text-sm font-mono font-bold ${pnlPct >= 0 ? 'text-green-400' : 'text-red-400'
                                }`}
                            >
                              {pnlPct >= 0 ? '+' : ''}
                              {pnlPct.toFixed(2)}%
                              <span className="text-xs text-white/40 ml-1">
                                ({row.unrealized_pnl >= 0 ? '+' : ''}₩{Math.round(row.unrealized_pnl).toLocaleString()})
                              </span>
                            </span>
                          </div>
                          {/* 게이지 바: 손절 ~ 익절 범위 */}
                          <div className="relative h-2 bg-white/[0.06] rounded-full overflow-hidden">
                            <motion.div
                              className={`h-full rounded-full ${barColor}`}
                              initial={{ width: 0 }}
                              animate={{ width: `${gauge}%` }}
                              transition={{ duration: 0.8 }}
                            />
                            {/* 손절선 마커 */}
                            <div
                              className="absolute top-0 h-full w-px bg-red-500/60"
                              style={{ left: '0%' } as CSSProperties}
                              title={`손절 ${stopLoss}%`}
                            />
                            {/* 익절선 마커 */}
                            <div
                              className="absolute top-0 h-full w-px bg-green-500/60"
                              style={{ left: '100%' } as CSSProperties}
                              title={`익절 +${takeProfit}%`}
                            />
                          </div>
                          <div className="flex justify-between mt-1">
                            <span className="text-[10px] text-red-400/60">손절 {stopLoss}%</span>
                            <span className="text-[10px] text-white/30">0%</span>
                            <span className="text-[10px] text-green-400/60">익절 +{takeProfit}%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* 일일 손익 vs 한도 */}
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-white/60">오늘 실현 손익 / 일일 한도</span>
                    <span
                      className={`text-sm font-mono font-semibold ${todayRealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'
                        }`}
                    >
                      {todayRealizedPnl >= 0 ? '+' : ''}₩{Math.round(todayRealizedPnl).toLocaleString()}
                      <span className="text-white/40 ml-1">
                        / {riskParams?.daily_loss_limit_pct ?? -5}%
                      </span>
                    </span>
                  </div>
                </div>
              </GlassCard>
            </motion.section>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {showAccuracyDetail && (
            <motion.section
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
            >
              <GlassCard className="p-5 space-y-4" hover={false}>
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2">
                  <div>
                    <h3 className="text-base font-semibold text-white">AI 정확도 이력</h3>
                    <p className="text-xs text-white/60">일별/주별/월별 승률 추이</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {([
                      { key: 'day', label: '일별' },
                      { key: 'week', label: '주별' },
                      { key: 'month', label: '월별' },
                    ] as const).map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => setAiRange(item.key)}
                        className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${aiRange === item.key
                          ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                          : 'bg-white/[0.02] border-white/10 text-white/70 hover:text-white'
                          }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <HistoryMetricCard
                    label="기간 정확도"
                    value={aiHistoryClosedTrades > 0 && aiHistoryAccuracy !== null ? `${aiHistoryAccuracy.toFixed(1)}%` : '—'}
                  />
                  <HistoryMetricCard label="수익 거래 수" value={`${aiHistoryWins}건`} />
                  <HistoryMetricCard label="종료 거래 수" value={`${aiHistoryClosedTrades}건`} />
                </div>

                <AccuracyLineChart points={aiHistoryPoints} />

                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-white/60 border-b border-white/10">
                        <th className="text-left py-2 pr-4">구간</th>
                        <th className="text-right py-2 pr-4">정확도</th>
                        <th className="text-right py-2 pr-4">승</th>
                        <th className="text-right py-2 pr-4">종료거래</th>
                      </tr>
                    </thead>
                    <tbody>
                      {aiHistoryPoints.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-6 text-center text-white/50">
                            표시할 이력이 없습니다.
                          </td>
                        </tr>
                      ) : (
                        aiHistoryPoints
                          .slice(-10)
                          .reverse()
                          .map((point) => (
                            <tr key={point.label} className="border-b border-white/5">
                              <td className="py-2 pr-4 text-white">{point.label}</td>
                              <td className="py-2 pr-4 text-right text-cyan-300">{point.accuracy.toFixed(1)}%</td>
                              <td className="py-2 pr-4 text-right text-green-400">{point.wins}</td>
                              <td className="py-2 pr-4 text-right text-white/80">{point.closed_trades}</td>
                            </tr>
                          ))
                      )}
                    </tbody>
                  </table>
                </div>
              </GlassCard>
            </motion.section>
          )}
        </AnimatePresence>

        <div aria-hidden="true" style={{ height: 64 }} />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <AIRecommendationCards />
        </motion.div>

        <motion.footer
          className="flex items-center justify-center gap-2 pt-8 pb-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
        >
          <span className="text-xs text-white/20 font-mono">
            CryptoAI Master v1.0 — Built with 🤖 Multi-Factor Scoring Engine
          </span>
        </motion.footer>
      </div>
    </div>
  );
}

interface StatusCardProps {
  icon: ReactNode;
  label: string;
  value: string;
  valueColorClass?: string;
  sub?: string;
  subColor?: string;
  actionLabel?: string;
  onClick?: () => void;
  clickable?: boolean;
  active?: boolean;
}

function StatusCard({
  icon,
  label,
  value,
  valueColorClass = 'text-white',
  sub = '',
  subColor = 'text-white/50',
  actionLabel,
  onClick,
  clickable = false,
  active = false,
}: StatusCardProps) {
  const useCardClick = clickable && !actionLabel;
  const hasActionButton = Boolean(actionLabel && onClick);
  return (
    <GlassCard
      className={`p-4 ${active ? 'ring-1 ring-cyan-400/60' : ''}`}
      hover={true}
      hoverScale={1.03}
      onClick={useCardClick ? onClick : undefined}
      role={useCardClick ? 'button' : undefined}
      tabIndex={useCardClick ? 0 : undefined}
      onKeyDown={
        useCardClick
          ? (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onClick?.();
            }
          }
          : undefined
      }
    >
      <div className={`relative flex flex-col items-center justify-center gap-2 text-center ${hasActionButton ? 'pr-20' : ''}`}>
        {hasActionButton && (
          <button
            type="button"
            onClick={onClick}
            className="absolute right-0 top-1/2 -translate-y-1/2 whitespace-nowrap rounded-md border border-cyan-400/40 bg-cyan-500/10 px-2 py-1 text-[11px] font-medium text-cyan-300 transition-colors hover:bg-cyan-500/20"
          >
            {actionLabel}
          </button>
        )}
        <div className="flex items-center justify-center gap-2">
          {icon}
          <span className="text-xs text-white/50 font-medium">{label}</span>
        </div>
        <div className={`text-lg font-bold font-mono ${valueColorClass}`}>{value}</div>
        {sub ? <span className={`text-xs ${subColor}`}>{sub}</span> : null}
      </div>
    </GlassCard>
  );
}

interface MetricCardProps {
  label: string;
  value: number | null;
  suffix?: string;
  positive?: boolean;
  positiveColorClass?: string;
  negativeColorClass?: string;
}

function MetricCard({
  label,
  value,
  suffix = '',
  positive,
  positiveColorClass = 'text-green-400',
  negativeColorClass = 'text-red-400',
}: MetricCardProps) {
  const textColor =
    typeof positive === 'boolean' ? (positive ? positiveColorClass : negativeColorClass) : 'text-white';

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
      <div className="text-xs text-white/60">{label}</div>
      <div className={`text-sm font-mono font-semibold ${textColor}`}>
        {value === null ? '조회 중...' : `₩${Math.round(value).toLocaleString()}${suffix}`}
      </div>
    </div>
  );
}

interface HistoryMetricCardProps {
  label: string;
  value: string;
}

function HistoryMetricCard({ label, value }: HistoryMetricCardProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2">
      <div className="text-xs text-white/60">{label}</div>
      <div className="text-sm font-mono font-semibold text-cyan-300">{value}</div>
    </div>
  );
}

interface AccuracyLineChartProps {
  points: AIAccuracyHistoryPoint[];
}

function AccuracyLineChart({ points }: AccuracyLineChartProps) {
  if (points.length === 0) {
    return (
      <div className="h-40 rounded-xl border border-white/10 bg-white/[0.02] flex items-center justify-center text-sm text-white/50">
        그래프 데이터 없음
      </div>
    );
  }

  const total = points.length;
  const coords = points
    .map((point, idx) => {
      const x = total === 1 ? 50 : (idx / (total - 1)) * 100;
      const y = 100 - Math.max(0, Math.min(100, point.accuracy));
      return `${x},${y}`;
    })
    .join(' ');

  const firstLabel = points[0]?.label ?? '';
  const middleLabel = points[Math.floor(points.length / 2)]?.label ?? '';
  const lastLabel = points[points.length - 1]?.label ?? '';

  return (
    <div>
      <div className="h-44 rounded-xl border border-white/10 bg-white/[0.02] p-3">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
          <line x1="0" y1="100" x2="100" y2="100" stroke="rgba(255,255,255,0.15)" strokeWidth="0.8" />
          <line x1="0" y1="50" x2="100" y2="50" stroke="rgba(255,255,255,0.10)" strokeWidth="0.6" />
          <line x1="0" y1="0" x2="100" y2="0" stroke="rgba(255,255,255,0.10)" strokeWidth="0.6" />

          <polyline
            points={coords}
            fill="none"
            stroke="rgba(0,217,255,0.95)"
            strokeWidth="1.6"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {points.map((point, idx) => {
            const x = total === 1 ? 50 : (idx / (total - 1)) * 100;
            const y = 100 - Math.max(0, Math.min(100, point.accuracy));
            return <circle key={`${point.label}-${idx}`} cx={x} cy={y} r="1.1" fill="rgba(0,217,255,0.95)" />;
          })}
        </svg>
      </div>
      <div className="mt-2 flex items-center justify-between text-[10px] text-white/45 font-mono">
        <span>{firstLabel}</span>
        <span>{middleLabel}</span>
        <span>{lastLabel}</span>
      </div>
    </div>
  );
}
