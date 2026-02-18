'use client';

/**
 * CryptoAI Master — 메인 대시보드 페이지
 *
 * 섹션 구성:
 *   1. 히어로 헤더 (앱 타이틀 + 시스템 상태)
 *   2. AI 추천 카드 (핵심)
 *   3. 시스템 상태 푸터
 */

import { motion } from 'framer-motion';
import {
  Bot,
  Activity,
  Shield,
  TrendingUp,
  Clock,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { AIRecommendationCards } from '@/components/dashboard/AIRecommendationCards';
import { GlassCard } from '@/components/ui/GlassCard';

export default function DashboardPage() {
  const [currentTime, setCurrentTime] = useState('');
  const [isOnline, setIsOnline] = useState(true);

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
        })
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

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

  return (
    <div className="min-h-screen grid-pattern">
      {/* ── 배경 파티클 ── */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        {[...Array(3)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-[500px] h-[500px] rounded-full"
            style={{
              background: `radial-gradient(circle, ${['rgba(0,217,255,0.03)', 'rgba(182,32,224,0.03)', 'rgba(0,255,135,0.03)'][i]
                } 0%, transparent 70%)`,
              left: `${[10, 60, 40][i]}%`,
              top: `${[20, 50, 70][i]}%`,
            }}
            animate={{
              x: [0, 30, -20, 0],
              y: [0, -20, 15, 0],
            }}
            transition={{
              duration: 15 + i * 5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
          />
        ))}
      </div>

      {/* ── 콘텐츠 ── */}
      <div
        className="relative z-10 max-w-[1440px] mx-auto space-y-8"
        style={{ padding: '33px 33px 48px 33px' }}
      >
        {/* ═══ 히어로 헤더 ═══ */}
        <motion.header
          className="space-y-4"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            {/* 로고 + 타이틀 */}
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

            {/* 상태 표시 */}
            <div className="flex items-center gap-3">
              {/* 시계 */}
              <GlassCard className="px-3 py-1.5" hover={false}>
                <div className="flex items-center gap-2">
                  <Clock size={13} className="text-white/40" />
                  <span className="text-xs font-mono text-white/70 tabular-nums">
                    {currentTime}
                  </span>
                </div>
              </GlassCard>

              {/* 온라인 */}
              <GlassCard className="px-3 py-1.5" hover={false}>
                <div className="flex items-center gap-2">
                  {isOnline ? (
                    <Wifi size={13} className="text-green-400" />
                  ) : (
                    <WifiOff size={13} className="text-red-400" />
                  )}
                  <span
                    className={`text-xs font-medium ${isOnline ? 'text-green-400/80' : 'text-red-400/80'
                      }`}
                  >
                    {isOnline ? 'LIVE' : 'OFFLINE'}
                  </span>
                </div>
              </GlassCard>

              {/* 모드 */}
              <GlassCard className="px-3 py-1.5" hover={false}>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
                  <span className="text-xs font-medium text-yellow-400/80">
                    🧪 PAPER
                  </span>
                </div>
              </GlassCard>
            </div>
          </div>
        </motion.header>

        {/* ═══ 상태 카드 로우 ═══ */}
        <motion.div
          className="grid grid-cols-2 sm:grid-cols-4 gap-3"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <StatusCard
            icon={<TrendingUp size={18} className="text-green-400" />}
            label="총 자산"
            value="₩1,000,000"
            sub="+0.00%"
            subColor="text-green-400"
          />
          <StatusCard
            icon={<Activity size={18} className="text-cyan-400" />}
            label="오늘 거래"
            value="0건"
            sub="₩0 수익"
            subColor="text-white/40"
          />
          <StatusCard
            icon={<Shield size={18} className="text-yellow-400" />}
            label="리스크"
            value="낮음"
            sub="포지션 0개"
            subColor="text-white/40"
          />
          <StatusCard
            icon={<Bot size={18} className="text-purple-400" />}
            label="AI 정확도"
            value="—"
            sub="데이터 수집 중"
            subColor="text-white/40"
          />
        </motion.div>

        {/* ═══ AI 추천 카드 (핵심) ═══ */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <AIRecommendationCards />
        </motion.div>

        {/* ═══ 푸터 ═══ */}
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

// ═══════════════════════════════════════════════════
// 상태 카드 서브 컴포넌트
// ═══════════════════════════════════════════════════

interface StatusCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  subColor: string;
}

function StatusCard({ icon, label, value, sub, subColor }: StatusCardProps) {
  return (
    <GlassCard className="p-4" hover={true} hoverScale={1.03}>
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs text-white/50 font-medium">{label}</span>
        </div>
        <div className="text-lg font-bold font-mono text-white">{value}</div>
        <span className={`text-xs ${subColor}`}>{sub}</span>
      </div>
    </GlassCard>
  );
}
