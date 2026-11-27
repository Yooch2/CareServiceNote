import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  // Docker 이미지에서만 standalone 서버로 빌드한다 (frontend/Dockerfile)
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
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
  // 화면과 API를 같은 출처로 묶어 세션 쿠키를 그대로 쓴다 (CORS 불필요).
  // 운영에서는 Caddy가 /api를 API로 바로 보내서 이 rewrite는 개발용이다 (deploy/Caddyfile)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
};

export default nextConfig;
