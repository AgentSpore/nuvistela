import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  // Dev only: keeps the API same-origin (cookies, no CORS). Production uses the reverse proxy.
  async rewrites() {
    if (process.env.NODE_ENV === "production") return [];
    const target = process.env.DEV_API_ORIGIN ?? "http://localhost:8080";
    return [{ source: "/api/:path*", destination: `${target}/api/:path*` }];
  },
};

export default withNextIntl(nextConfig);
