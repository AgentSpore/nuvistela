/** Same-origin proxy for /api when the build knows the backend origin; otherwise a reverse proxy serves it. */
export function apiRewrites(origin: string | undefined) {
  return origin ? [{ source: "/api/:path*", destination: `${origin}/api/:path*` }] : [];
}
