import type { NextConfig } from "next";

const apiProxyBase = process.env.API_PROXY_BASE_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiProxyBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
