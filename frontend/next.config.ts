import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // 화면과 API를 같은 출처로 묶어 세션 쿠키를 그대로 쓴다 (CORS 불필요)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
};

export default nextConfig;
