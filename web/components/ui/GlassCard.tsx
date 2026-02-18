'use client';

/**
 * GlassCard — 글라스모피즘 카드 컴포넌트
 *
 * 반투명 배경 + 블러 + 네온 글로우 테두리.
 * glow 프롭으로 카드 주변 네온 색상을 제어합니다.
 *
 * @example
 * <GlassCard glow="green" className="p-6">
 *   <h2>BTC</h2>
 * </GlassCard>
 */

import { motion, HTMLMotionProps } from 'framer-motion';
import { ReactNode } from 'react';

type GlowColor = 'green' | 'pink' | 'cyan' | 'yellow' | 'purple' | 'none';

interface GlassCardProps extends Omit<HTMLMotionProps<'div'>, 'children'> {
    /** 자식 노드 */
    children: ReactNode;
    /** 추가 CSS 클래스 */
    className?: string;
    /** 네온 글로우 색상 (기본: none) */
    glow?: GlowColor;
    /** 호버 시 스케일 효과 (기본: true) */
    hover?: boolean;
    /** 호버 스케일 크기 (기본: 1.02) */
    hoverScale?: number;
    /** 패딩 프리셋 */
    padding?: 'none' | 'sm' | 'md' | 'lg';
}

const glowShadows: Record<GlowColor, string> = {
    green: '0 0 30px rgba(0,255,135,0.25), 0 0 60px rgba(0,255,135,0.10)',
    pink: '0 0 30px rgba(255,0,85,0.25), 0 0 60px rgba(255,0,85,0.10)',
    cyan: '0 0 30px rgba(0,217,255,0.25), 0 0 60px rgba(0,217,255,0.10)',
    yellow: '0 0 30px rgba(255,214,0,0.25), 0 0 60px rgba(255,214,0,0.10)',
    purple: '0 0 30px rgba(182,32,224,0.25), 0 0 60px rgba(182,32,224,0.10)',
    none: 'none',
};

const glowHoverShadows: Record<GlowColor, string> = {
    green: '0 0 40px rgba(0,255,135,0.40), 0 0 80px rgba(0,255,135,0.15)',
    pink: '0 0 40px rgba(255,0,85,0.40), 0 0 80px rgba(255,0,85,0.15)',
    cyan: '0 0 40px rgba(0,217,255,0.40), 0 0 80px rgba(0,217,255,0.15)',
    yellow: '0 0 40px rgba(255,214,0,0.40), 0 0 80px rgba(255,214,0,0.15)',
    purple: '0 0 40px rgba(182,32,224,0.40), 0 0 80px rgba(182,32,224,0.15)',
    none: 'none',
};

const paddingMap = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
};

export function GlassCard({
    children,
    className = '',
    glow = 'none',
    hover = true,
    hoverScale = 1.02,
    padding = 'none',
    ...motionProps
}: GlassCardProps) {
    return (
        <motion.div
            className={`
        relative overflow-hidden rounded-2xl
        bg-gradient-to-br from-white/[0.05] to-white/[0.02]
        backdrop-blur-xl border border-white/10
        transition-colors duration-300
        hover:border-white/20
        ${paddingMap[padding]}
        ${className}
      `}
            style={{ boxShadow: glowShadows[glow] }}
            whileHover={
                hover
                    ? { scale: hoverScale, boxShadow: glowHoverShadows[glow] }
                    : undefined
            }
            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            {...motionProps}
        >
            {/* 내부 오버레이 그라데이션 */}
            <div
                className="absolute inset-0 opacity-50 pointer-events-none"
                style={{
                    background:
                        'linear-gradient(135deg, rgba(0,217,255,0.03) 0%, transparent 50%, rgba(182,32,224,0.03) 100%)',
                }}
            />

            {/* 콘텐츠 */}
            <div className="relative z-10">{children}</div>
        </motion.div>
    );
}

export default GlassCard;
