import type { NextConfig } from "next";

// Where the browser sends questions. The API address is public -- every visitor's
// browser sees it -- so it lives here rather than in a hosting secret. An explicit
// NEXT_PUBLIC_API_BASE still wins; otherwise a Vercel build (VERCEL is set by the
// platform) points at the hosted API, and a local build at the local one.
const apiBase =
  process.env.NEXT_PUBLIC_API_BASE ??
  (process.env.VERCEL ? "https://ugbs-navigator-api.onrender.com" : "http://localhost:8000");

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE: apiBase,
  },
};

export default nextConfig;
