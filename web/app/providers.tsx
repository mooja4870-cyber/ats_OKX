'use client';

/**
 * Providers — 앱 전역 프로바이더 래퍼
 *
 * TanStack Query, Toast, 테마 등을 한 곳에서 관리합니다.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { ReactNode, useState } from 'react';

export function Providers({ children }: { children: ReactNode }) {
    const [queryClient] = useState(
        () =>
            new QueryClient({
                defaultOptions: {
                    queries: {
                        retry: 2,
                        staleTime: 10_000,
                        refetchOnWindowFocus: true,
                    },
                },
            })
    );

    return (
        <QueryClientProvider client={queryClient}>
            {children}
            <Toaster
                position="top-right"
                theme="dark"
                richColors
                toastOptions={{
                    style: {
                        background: 'rgba(21, 27, 59, 0.95)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        backdropFilter: 'blur(20px)',
                        color: '#fff',
                    },
                }}
            />
        </QueryClientProvider>
    );
}
