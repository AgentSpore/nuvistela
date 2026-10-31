import { describe, expect, it } from "vitest";
import { apiRewrites } from "@/lib/api-rewrites";

describe("apiRewrites", () => {
  it("proxies /api to the origin when API_ORIGIN is set, whatever NODE_ENV is", () => {
    expect(apiRewrites("http://backend:8080")).toEqual([
      { source: "/api/:path*", destination: "http://backend:8080/api/:path*" },
    ]);
  });
  it("is empty without API_ORIGIN (a reverse proxy serves /api)", () => {
    expect(apiRewrites(undefined)).toEqual([]);
    expect(apiRewrites("")).toEqual([]);
  });
});
