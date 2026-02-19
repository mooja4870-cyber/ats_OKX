import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cosmic: {
          900: '#0A0E27',
          800: '#151B3B',
        },
        neon: {
          green: '#00FF87',
          pink: '#FF0055',
          yellow: '#FFD600',
          cyan: '#00D9FF',
          purple: '#B620E0',
        },
      },
      fontFamily: {
        heading: ['Space Grotesk', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        'glow-green': '0 0 20px rgba(0,255,135,0.5)',
        'glow-pink': '0 0 20px rgba(255,0,85,0.5)',
        'glow-cyan': '0 0 20px rgba(0,217,255,0.5)',
      },
    },
  },
  plugins: [],
};

export default config;
