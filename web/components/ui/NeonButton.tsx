'use client';

/**
 * NeonButton — 네온 글로우 버튼
 *
 * 그라데이션 배경 + 글로우 쉐도우 + 호버/탭 모션.
 *
 * @example
 * <NeonButton variant="success" size="md" onClick={handleBuy}>
 *   💰 지금 매수
 * </NeonButton>
 */

import { motion, HTMLMotionProps } from 'framer-motion';
import { ReactNode, forwardRef } from 'react';

type ButtonVariant = 'primary' | 'success' | 'danger' | 'warning' | 'ghost';
type ButtonSize = 'xs' | 'sm' | 'md' | 'lg';

interface NeonButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
    /** 버튼 텍스트/아이콘 */
    children: ReactNode;
    /** 스타일 변형 (기본: primary) */
    variant?: ButtonVariant;
    /** 크기 (기본: md) */
    size?: ButtonSize;
    /** 전체 너비 (기본: false) */
    fullWidth?: boolean;
    /** 로딩 중 */
    loading?: boolean;
    /** 비활성 */
    disabled?: boolean;
    /** CSS 클래스 */
    className?: string;
}

const variantStyles: Record<ButtonVariant, {
    gradient: string;
    glow: string;
    hoverGlow: string;
    text: string;
}> = {
    primary: {
        gradient: 'from-cyan-500 to-blue-600',
        glow: '0 0 20px rgba(0,217,255,0.3)',
        hoverGlow: '0 0 35px rgba(0,217,255,0.5)',
        text: 'text-white',
    },
    success: {
        gradient: 'from-green-500 to-emerald-600',
        glow: '0 0 20px rgba(0,255,135,0.3)',
        hoverGlow: '0 0 35px rgba(0,255,135,0.5)',
        text: 'text-white',
    },
    danger: {
        gradient: 'from-pink-500 to-rose-600',
        glow: '0 0 20px rgba(255,0,85,0.3)',
        hoverGlow: '0 0 35px rgba(255,0,85,0.5)',
        text: 'text-white',
    },
    warning: {
        gradient: 'from-yellow-500 to-orange-500',
        glow: '0 0 20px rgba(255,214,0,0.3)',
        hoverGlow: '0 0 35px rgba(255,214,0,0.5)',
        text: 'text-black',
    },
    ghost: {
        gradient: '',
        glow: 'none',
        hoverGlow: '0 0 20px rgba(255,255,255,0.1)',
        text: 'text-white/70 hover:text-white',
    },
};

const sizeStyles: Record<ButtonSize, string> = {
    xs: 'px-3 py-1.5 text-xs rounded-lg gap-1',
    sm: 'px-4 py-2 text-sm rounded-xl gap-1.5',
    md: 'px-6 py-3 text-base rounded-xl gap-2',
    lg: 'px-8 py-4 text-lg rounded-2xl gap-2.5',
};

export function NeonButton({
    children,
    variant = 'primary',
    size = 'md',
    fullWidth = false,
    loading = false,
    disabled = false,
    className = '',
    ...motionProps
}: NeonButtonProps) {
    const v = variantStyles[variant];
    const isGhost = variant === 'ghost';

    return (
        <motion.button
            className={`
        relative inline-flex items-center justify-center
        font-semibold font-body
        ${sizeStyles[size]}
        ${v.text}
        ${fullWidth ? 'w-full' : ''}
        ${isGhost
                    ? 'border border-white/10 hover:border-white/20 bg-white/[0.03]'
                    : `bg-gradient-to-r ${v.gradient}`
                }
        ${disabled || loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        transition-all duration-300
        ${className}
      `}
            style={{ boxShadow: disabled ? 'none' : v.glow }}
            whileHover={
                !disabled && !loading
                    ? { scale: 1.04, boxShadow: v.hoverGlow }
                    : undefined
            }
            whileTap={
                !disabled && !loading ? { scale: 0.96 } : undefined
            }
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            disabled={disabled || loading}
            {...motionProps}
        >
            {/* 배경 쉬머 효과 */}
            {!isGhost && !disabled && (
                <div
                    className="absolute inset-0 rounded-[inherit] opacity-30"
                    style={{
                        background:
                            'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.15) 50%, transparent 100%)',
                        backgroundSize: '200% 100%',
                        animation: 'shimmer 3s ease-in-out infinite',
                    }}
                />
            )}

            {/* 로딩 스피너 */}
            {loading && (
                <svg
                    className="animate-spin h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                >
                    <circle
                        className="opacity-25"
                        cx="12" cy="12" r="10"
                        stroke="currentColor" strokeWidth="4"
                    />
                    <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                </svg>
            )}

            {/* 콘텐츠 */}
            <span className="relative z-10">{children}</span>
        </motion.button>
    );
}

export default NeonButton;
