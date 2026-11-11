import type { NextConfig } from "next";

const API_ORIGIN = process.env.WARDSIGHT_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // WARDSIGHT_RECORDING=1 npm run dev hides the Next.js dev badge for screen recordings.
  devIndicators: process.env.WARDSIGHT_RECORDING === "1" ? false : {},
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // The Python API (FastAPI) serves /api; the browser only ever talks to this app.
  // The hosted public demo has no API at all, so nothing is forwarded there.
  rewrites() {
    if (process.env.NEXT_PUBLIC_WARDSIGHT_MODE === "public") return [];
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
