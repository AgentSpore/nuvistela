import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";
import { apiRewrites } from "./src/lib/api-rewrites";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  // Baked in at build time. Unset where a reverse proxy (Caddy, K5) serves /api.
  // File names under public/worlds carry a content hash, so they never change in place.
  async headers() {
    return [
      {
        source: "/worlds/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
    ];
  },
  async rewrites() {
    return apiRewrites(process.env.API_ORIGIN);
  },
};

export default withNextIntl(nextConfig);
