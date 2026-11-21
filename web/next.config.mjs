/** Next.js config. Merchant images load straight from merchant URLs (never re-hosted). */
import path from "node:path";
import { fileURLToPath } from "node:url";

const nextConfig = {
  // Pin the workspace root so Next ignores unrelated lockfiles higher up the disk.
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
};
export default nextConfig;
