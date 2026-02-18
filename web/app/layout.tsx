import type { Metadata } from 'next';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'CryptoAI Master — 24시간 AI 자동매매',
  description:
    '멀티팩터 AI 스코어링 기반 암호화폐 자동매매 대시보드. BTC, ETH, XRP, SOL 실시간 분석.',
  keywords: ['crypto', 'AI', 'trading', 'bitcoin', 'dashboard'],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
      </head>
      <body className="bg-cosmic-900 text-white antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
