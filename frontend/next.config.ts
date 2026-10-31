import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";
import { apiRewrites } from "./src/lib/api-rewrites";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  // Baked in at build time. Unset where a reverse proxy (Caddy, K5) serves /api.
  async rewrites() {
    return apiRewrites(process.env.API_ORIGIN);
  },
};

export default withNextIntl(nextConfig);
