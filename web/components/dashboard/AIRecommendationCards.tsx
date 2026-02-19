'use client';

/**
 * AIRecommendationCards — AI 추천 카드 (핵심 컴포넌트)
 *
 * 멀티팩터 스코어링 결과를 게임 UI 스타일로 표시합니다.
 * TanStack Query로 30초마다 API에서 스코어를 갱신합니다.
 *
 * ■ CoinCard 레이아웃:
 *   ┌────────────────────────────────┐
 *   │  🪙 BTC      [🔥 STRONG BUY]  │ ← 헤더 + 시그널 배지
 *   │  ₩143,250,000                 │ ← 현재가
 *   │                               │
 *   │  AI 점수                 93점  │ ← 점수 텍스트
 *   │  ███████████████░░░░░   93%   │ ← 프로그레스 바
 *   │                               │
 *   │  📊 기술(85) 📈 모멘텀(91)     │ ← 5팩터 미니 차트
 *   │  📉 변동(72) 📊 거래(88)      │
 *   │  💬 심리(65)                   │
 *   │                               │
 *   │  RSI 과매도 구간 진입...       │ ← AI 추론
 *   │                               │
 *   │  신뢰도       ███████░  78%   │ ← 신뢰도 바
 *   │  [   💰 지금 매수   ]          │ ← CTA 버튼
 *   └────────────────────────────────┘
 */

import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Flame,
    TrendingUp,
    TrendingDown,
    ShieldAlert,
    BarChart3,
    Activity,
    Zap,
    Wind,
    MessageCircle,
    RefreshCw,
    AlertCircle,
} from 'lucide-react';
import { GlassCard } from '@/components/ui/GlassCard';
import { NeonButton } from '@/components/ui/NeonButton';
import { toast } from 'sonner';

// ═══════════════════════════════════════════════════
// 타입 정의
// ═══════════════════════════════════════════════════

/** 백엔드 스코어링 API 응답 */
interface CoinScore {
    symbol: string;
    name?: string;
    current_price?: number;
    price_change_24h?: number;
    technical_score: number;
    momentum_score: number;
    volatility_score: number;
    volume_score: number;
    sentiment_score: number;
    total_score: number;
    signal: 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL';
    confidence: number;
    reasoning: string;
}

interface CoinMeta {
    emoji: string;
    name: string;
    color: string;
}

// ═══════════════════════════════════════════════════
// 상수
// ═══════════════════════════════════════════════════

const COIN_META: Record<string, CoinMeta> = {
    BTC: { emoji: '🪙', name: 'Bitcoin', color: '#F7931A' },
    ETH: { emoji: '💠', name: 'Ethereum', color: '#627EEA' },
    XRP: { emoji: '🌊', name: 'Ripple', color: '#00AAE4' },
    SOL: { emoji: '☀️', name: 'Solana', color: '#9945FF' },
};

const SIGNAL_CONFIG = {
    STRONG_BUY: {
        gradient: 'from-green-400 to-emerald-500',
        bg: 'bg-green-500/20',
        glow: 'green' as const,
        icon: Flame,
        iconColor: 'text-orange-400',
        label: '🔥 강력 매수',
        pulse: true,
        barColor: 'from-green-400 to-emerald-400',
    },
    BUY: {
        gradient: 'from-cyan-400 to-blue-500',
        bg: 'bg-cyan-500/20',
        glow: 'cyan' as const,
        icon: TrendingUp,
        iconColor: 'text-cyan-400',
        label: '🟢 매수',
        pulse: false,
        barColor: 'from-cyan-400 to-blue-400',
    },
    HOLD: {
        gradient: 'from-yellow-400 to-orange-400',
        bg: 'bg-yellow-500/10',
        glow: 'none' as const,
        icon: ShieldAlert,
        iconColor: 'text-yellow-400',
        label: '🟡 대기',
        pulse: false,
        barColor: 'from-yellow-400 to-orange-400',
    },
    SELL: {
        gradient: 'from-pink-500 to-rose-500',
        bg: 'bg-pink-500/10',
        glow: 'pink' as const,
        icon: TrendingDown,
        iconColor: 'text-pink-400',
        label: '🔴 매도',
        pulse: false,
        barColor: 'from-pink-500 to-rose-500',
    },
};

const FACTOR_META = [
    { key: 'technical_score', label: '기술', icon: BarChart3, color: 'text-cyan-400' },
    { key: 'momentum_score', label: '모멘텀', icon: Activity, color: 'text-green-400' },
    { key: 'volatility_score', label: '변동', icon: Wind, color: 'text-yellow-400' },
    { key: 'volume_score', label: '거래량', icon: Zap, color: 'text-purple-400' },
    { key: 'sentiment_score', label: '심리', icon: MessageCircle, color: 'text-pink-400' },
] as const;

// ═══════════════════════════════════════════════════
// 메인 컴포넌트
// ═══════════════════════════════════════════════════

export function AIRecommendationCards() {
    const { data: systemConfig } = useQuery<
        { trading_mode?: string },
        Error,
        { trading_mode?: string },
        string[]
    >({
        queryKey: ['system-config'],
        queryFn: async () => {
            const res = await fetch('/api/system/config');
            if (!res.ok) {
                throw new Error(`API ${res.status}`);
            }
            return res.json() as Promise<{ trading_mode?: string }>;
        },
        refetchInterval: 10_000,
        staleTime: 5_000,
    });

    const fetchScores = async (): Promise<CoinScore[]> => {
        const res = await fetch('/api/coins/scores');
        if (!res.ok) throw new Error(`API ${res.status}`);
        return res.json();
    };

    const scoresQuery = useQuery({
        queryKey: ['coin-scores'] as const,
        queryFn: fetchScores,
        refetchInterval: 10_000,
        staleTime: 5_000,
        retry: 2,
        retryDelay: (attempt: number) => Math.min(1000 * 2 ** attempt, 5000),
    });

    const scores = scoresQuery.data as CoinScore[] | undefined;
    const { isLoading, isError, refetch, isFetching } = scoresQuery;

    const tradingMode = (systemConfig?.trading_mode ?? '').toLowerCase();
    const allowManualBuy = tradingMode === 'paper';

    if (isLoading && (!scores || scores.length === 0)) {
        return <LoadingSkeleton />;
    }

    if (!scores || scores.length === 0) {
        if (isError) {
            return (
                <section className="space-y-4">
                    <div className="flex items-center gap-2 text-sm text-red-400/90">
                        <AlertCircle size={16} />
                        AI 추천 데이터를 불러오지 못했습니다. API/DB 상태를 확인해 주세요.
                    </div>
                    <NeonButton variant="danger" size="sm" onClick={() => refetch()}>
                        다시 시도
                    </NeonButton>
                </section>
            );
        }
        return (
            <section className="space-y-4">
                <div className="text-sm text-white/70">
                    표시할 AI 추천 데이터가 없습니다.
                </div>
            </section>
        );
    }

    // 점수 내림차순 정렬
    const sorted = [...scores].sort((a, b) => b.total_score - a.total_score);

    return (
        <section className="space-y-6">
            {isError && (
                <div className="flex items-center gap-2 text-xs text-yellow-300/90">
                    <AlertCircle size={14} />
                    업비트 응답 지연으로 이전 데이터를 유지 중입니다.
                </div>
            )}
            {/* 섹션 헤더 */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shadow-glow-purple">
                        <span className="text-xl">🤖</span>
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold font-heading text-white">
                            AI 추천
                        </h2>
                        <p className="text-xs text-white/40 font-mono">
                            MULTI-FACTOR SCORING ENGINE
                        </p>
                    </div>
                </div>

                {/* 새로고침 */}
                <NeonButton
                    variant="ghost"
                    size="xs"
                    onClick={() => refetch()}
                    loading={isFetching}
                >
                    <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
                    갱신
                </NeonButton>
            </div>

            {/* 카드 그리드 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                <AnimatePresence mode="popLayout">
                    {sorted.map((coin, index) => (
                        <CoinCard
                            key={coin.symbol}
                            coin={coin}
                            meta={COIN_META[coin.symbol] ?? { emoji: '🔷', name: coin.symbol, color: '#888' }}
                            index={index}
                            allowManualBuy={allowManualBuy}
                        />
                    ))}
                </AnimatePresence>
            </div>
        </section>
    );
}

// ═══════════════════════════════════════════════════
// CoinCard 서브 컴포넌트
// ═══════════════════════════════════════════════════

interface CoinCardProps {
    coin: CoinScore;
    meta: CoinMeta;
    index: number;
    allowManualBuy: boolean;
}

function CoinCard({ coin, meta, index, allowManualBuy }: CoinCardProps) {
    const config = SIGNAL_CONFIG[coin.signal];
    const SignalIcon = config.icon;
    const signalText =
        coin.signal === 'STRONG_BUY'
            ? '강매수'
            : coin.signal === 'BUY'
                ? '매수'
                : coin.signal === 'SELL'
                    ? '매도'
                    : '';
    const signalDotClass =
        coin.signal === 'STRONG_BUY'
            ? 'bg-emerald-400'
            : coin.signal === 'BUY'
                ? 'bg-cyan-400'
                : coin.signal === 'SELL'
                    ? 'bg-rose-400'
                    : 'bg-yellow-300';
    const isPriceUp = typeof coin.price_change_24h === 'number' && coin.price_change_24h > 0;
    const isPriceDown = typeof coin.price_change_24h === 'number' && coin.price_change_24h < 0;
    const priceColorClass = isPriceUp ? 'text-red-400' : isPriceDown ? 'text-blue-400' : 'text-white';
    const changeColorClass = isPriceUp ? 'text-red-400' : isPriceDown ? 'text-blue-400' : 'text-white';

    // 매수 핸들러
    const handleBuy = async () => {
        const amount = 100_000;
        if (
            !confirm(
                `${meta.emoji} ${coin.symbol}을(를) ₩${amount.toLocaleString()} 매수하시겠습니까?`
            )
        )
            return;

        try {
            const res = await fetch('/api/trades/order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: coin.symbol,
                    side: 'BUY',
                    amount,
                    order_type: 'MARKET',
                }),
            });

            if (res.ok) {
                toast.success(`${meta.emoji} ${coin.symbol} 매수 주문 완료!`, {
                    description: `₩${amount.toLocaleString()} 시장가 주문`,
                });
            } else {
                const body = await res.json().catch(() => ({} as { detail?: string }));
                toast.error(`매수 실패: ${body.detail || res.statusText}`);
            }
        } catch {
            toast.error('네트워크 오류가 발생했습니다');
        }
    };

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{
                type: 'spring',
                stiffness: 260,
                damping: 20,
                delay: index * 0.08,
            }}
        >
            <GlassCard glow={config.glow} className="p-5 h-full">
                {/* ── STRONG_BUY 펄스 배경 ── */}
                {config.pulse && (
                    <motion.div
                        className="absolute inset-0 rounded-2xl"
                        style={{
                            background:
                                'linear-gradient(135deg, rgba(0,255,135,0.08) 0%, rgba(0,255,135,0.03) 100%)',
                        }}
                        animate={{
                            opacity: [0.4, 0.8, 0.4],
                            scale: [1, 1.01, 1],
                        }}
                        transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
                    />
                )}

                <div className="relative space-y-4">
                    {/* ── 헤더: 코인 + 시그널 배지 ── */}
                    <div className="relative">
                        {/* 시그널 배지 */}
                        <div
                            className={`
                absolute right-0 top-0 px-2.5 py-1 rounded-full flex items-center gap-1.5
                ${config.bg} border border-white/10
              `}
                        >
                            <SignalIcon size={14} className={config.iconColor} />
                            <span className={`w-2 h-2 rounded-full ${signalDotClass}`} />
                            {signalText ? (
                                <span className="text-[11px] font-bold text-white/90">
                                    {signalText}
                                </span>
                            ) : null}
                        </div>

                        <div className="flex flex-col items-center text-center gap-0.5">
                            <span className="text-3xl drop-shadow-lg">{meta.emoji}</span>
                            <h3 className="text-lg font-bold text-white font-heading">
                                {coin.symbol}
                            </h3>
                            <span className="text-xs text-white/40">{meta.name}</span>
                        </div>
                    </div>

                    {/* ── 현재가 ── */}
                    {coin.current_price && (
                        <div className="flex items-baseline justify-center gap-2 text-center">
                            <span className={`text-xl font-bold font-mono ${priceColorClass}`}>
                                ₩{coin.current_price.toLocaleString()}
                            </span>
                            {coin.price_change_24h !== undefined && (
                                <span
                                    className={`text-xs font-semibold ${changeColorClass}`}
                                >
                                    {coin.price_change_24h >= 0 ? '+' : ''}
                                    {coin.price_change_24h.toFixed(2)}%
                                </span>
                            )}
                        </div>
                    )}

                    {/* ── AI 종합 점수 ── */}
                    <div>
                        <div className="flex items-center justify-between mb-1.5">
                            <span className="text-xs text-white/50 font-medium">
                                AI 종합 점수
                            </span>
                            <span className="text-2xl font-black font-mono text-gradient-cyan">
                                {Math.round(coin.total_score)}
                                <span className="text-sm font-medium text-white/40 ml-0.5">점</span>
                            </span>
                        </div>

                        {/* 프로그레스 바 */}
                        <div className="h-2.5 bg-white/[0.06] rounded-full overflow-hidden">
                            <motion.div
                                className={`h-full rounded-full bg-gradient-to-r ${config.barColor}`}
                                initial={{ width: 0 }}
                                animate={{ width: `${coin.total_score}%` }}
                                transition={{ duration: 1.2, delay: index * 0.08, ease: 'easeOut' }}
                            />
                        </div>
                    </div>

                    {/* ── 5팩터 미니 차트 ── */}
                    <div className="grid grid-cols-5 gap-1.5">
                        {FACTOR_META.map(({ key, label, icon: Icon, color }) => {
                            const value = coin[key as keyof CoinScore] as number;
                            return (
                                <div key={key} className="text-center space-y-1">
                                    <Icon size={12} className={`mx-auto ${color} opacity-70`} />
                                    <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                                        <motion.div
                                            className={`h-full rounded-full bg-gradient-to-r ${config.barColor}`}
                                            initial={{ width: 0 }}
                                            animate={{ width: `${value}%` }}
                                            transition={{ duration: 0.8, delay: index * 0.08 + 0.3 }}
                                        />
                                    </div>
                                    <div className="text-[10px] text-white/40 leading-none">{label}</div>
                                    <div className="text-[10px] font-mono text-white/70 font-semibold">
                                        {Math.round(value)}
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* ── AI 추론 텍스트 ── */}
                    <p className="text-xs text-white/60 leading-relaxed line-clamp-2 min-h-[2.5rem]">
                        {coin.reasoning}
                    </p>

                    {/* ── 신뢰도 ── */}
                    <div className="flex items-center gap-2">
                        <span className="text-[10px] text-white/40 whitespace-nowrap">
                            신뢰도
                        </span>
                        <div className="flex-1 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                            <motion.div
                                className="h-full rounded-full bg-gradient-to-r from-cyan-400/80 to-blue-500/80"
                                initial={{ width: 0 }}
                                animate={{ width: `${coin.confidence}%` }}
                                transition={{ duration: 1, delay: index * 0.08 + 0.5 }}
                            />
                        </div>
                        <span className="text-[10px] font-mono text-white/60 font-semibold tabular-nums">
                            {Math.round(coin.confidence)}%
                        </span>
                    </div>

                    {/* ── CTA 버튼 ── */}
                    {allowManualBuy && (coin.signal === 'STRONG_BUY' || coin.signal === 'BUY') && (
                        <NeonButton
                            variant="success"
                            size="sm"
                            fullWidth
                            onClick={handleBuy}
                            className="mt-1"
                        >
                            💰 지금 매수
                        </NeonButton>
                    )}
                </div>
            </GlassCard>
        </motion.div>
    );
}

// ═══════════════════════════════════════════════════
// 로딩 스켈레톤
// ═══════════════════════════════════════════════════

function LoadingSkeleton() {
    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-white/5 animate-pulse" />
                <div className="space-y-2">
                    <div className="h-6 w-32 bg-white/5 rounded animate-pulse" />
                    <div className="h-3 w-48 bg-white/5 rounded animate-pulse" />
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                {[0, 1, 2, 3].map((i) => (
                    <GlassCard key={i} className="p-5" hover={false}>
                        <div className="space-y-4">
                            {/* 헤더 스켈레톤 */}
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-9 h-9 rounded-full bg-white/5 animate-pulse" />
                                    <div className="space-y-1.5">
                                        <div className="h-4 w-12 bg-white/5 rounded animate-pulse" />
                                        <div className="h-3 w-16 bg-white/5 rounded animate-pulse" />
                                    </div>
                                </div>
                                <div className="h-6 w-20 bg-white/5 rounded-full animate-pulse" />
                            </div>

                            {/* 점수 스켈레톤 */}
                            <div className="space-y-2">
                                <div className="flex justify-between">
                                    <div className="h-3 w-16 bg-white/5 rounded animate-pulse" />
                                    <div className="h-6 w-14 bg-white/5 rounded animate-pulse" />
                                </div>
                                <div className="h-2.5 bg-white/5 rounded-full animate-pulse" />
                            </div>

                            {/* 5팩터 스켈레톤 */}
                            <div className="grid grid-cols-5 gap-1.5">
                                {[0, 1, 2, 3, 4].map((j) => (
                                    <div key={j} className="space-y-1 text-center">
                                        <div className="w-3 h-3 mx-auto bg-white/5 rounded animate-pulse" />
                                        <div className="h-1 bg-white/5 rounded-full animate-pulse" />
                                        <div className="h-2 w-6 mx-auto bg-white/5 rounded animate-pulse" />
                                    </div>
                                ))}
                            </div>

                            {/* 텍스트 스켈레톤 */}
                            <div className="space-y-1.5">
                                <div className="h-3 w-full bg-white/5 rounded animate-pulse" />
                                <div className="h-3 w-3/4 bg-white/5 rounded animate-pulse" />
                            </div>

                            {/* 신뢰도 스켈레톤 */}
                            <div className="h-1 bg-white/5 rounded-full animate-pulse" />
                        </div>
                    </GlassCard>
                ))}
            </div>
        </div>
    );
}

export default AIRecommendationCards;
