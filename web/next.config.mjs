/**
 * Next.js config. Merchant images load straight from merchant URLs (never re-hosted).
 * Desk mode, "See it here" and the scene walk-through are cut from the flow: their routes
 * redirect to the start screen unless NEXT_PUBLIC_SHOW_EXTRAS=1 (the files are kept).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const showExtras = process.env.NEXT_PUBLIC_SHOW_EXTRAS === "1";
// Optional same-origin proxy to the FastAPI backend (no CORS, any dev port): set
// API_PROXY_TARGET=http://localhost:8010 and NEXT_PUBLIC_API_URL=/backend.
const apiTarget = process.env.API_PROXY_TARGET;

const nextConfig = {
  // Pin the workspace root so Next ignores unrelated lockfiles higher up the disk.
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  // "See it here" uploads a photo or video (up to 60 MB) through the /backend proxy: allow big bodies
  // (the default buffers only 10 MB) and give the backend time to extract frames.
  experimental: { middlewareClientMaxBodySize: "64mb", proxyTimeout: 120_000 },
  async rewrites() {
    return apiTarget ? [{ source: "/backend/:path*", destination: `${apiTarget}/:path*` }] : [];
  },
  async redirects() {
    if (showExtras) return [];
    return ["/desk", "/see-it", "/scene"].map((source) => ({ source, destination: "/", permanent: false }));
  },
};
export default nextConfig;
