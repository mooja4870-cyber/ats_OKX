export const colors = {
  background: {
    primary: '#0A0E27',
    secondary: '#151B3B',
    card: 'rgba(255,255,255,0.03)',
  },
  brand: {
    neonGreen: '#00FF87',
    neonPink: '#FF0055',
    neonYellow: '#FFD600',
    cyberBlue: '#00D9FF',
    purple: '#B620E0',
  },
  text: {
    primary: '#FFFFFF',
    secondary: 'rgba(255,255,255,0.7)',
  },
} as const;

export const typography = {
  fontFamily: {
    primary: 'Inter, sans-serif',
    mono: 'JetBrains Mono, monospace',
    heading: 'Space Grotesk, sans-serif',
  },
  fontSize: {
    xs: '12px',
    sm: '14px',
    base: '16px',
    lg: '18px',
    xl: '24px',
    '2xl': '32px',
    '3xl': '48px',
    hero: '72px',
  },
} as const;

export const animation = {
  duration: {
    fast: '150ms',
    normal: '300ms',
    slow: '500ms',
  },
} as const;
