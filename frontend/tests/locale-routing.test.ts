import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import proxy from "../src/proxy";

const request = (path: string, cookie?: string) =>
  new NextRequest(`http://localhost${path}`, {
    headers: cookie ? { cookie: `NEXT_LOCALE=${cookie}` } : undefined,
  });

describe("es and zh-CN locales", () => {
  it.each(["es", "zh-CN"])("serves the %s landing", (locale) => {
    const response = proxy(request(`/${locale}`));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });
  it.each(["new", "play", "family", "join"])("serves the %s app route", (path) => {
    for (const locale of ["es", "zh-CN"]) {
      const response = proxy(request(`/${locale}/${path}`));
      expect(response.status).toBe(200);
      expect(response.headers.get("location")).toBeNull();
    }
  });
  it.each(["/new", "/join/abc"])(
    "sends a stored es or zh-CN choice on %s to its prefix",
    (path) => {
      for (const locale of ["es", "zh-CN"]) {
        const stored = proxy(request(path, locale));
        expect(new URL(stored.headers.get("location") ?? "").pathname).toBe(
          `/${locale}${path}`,
        );
      }
    },
  );
  it.each(["/new", "/join/abc"])(
    "keeps %s in the default locale when only Accept-Language says es",
    (path) => {
      const response = proxy(
        new NextRequest(`http://localhost${path}`, {
          headers: { "accept-language": "es-ES,es;q=0.9" },
        }),
      );
      expect(response.headers.get("location")).toBeNull();
      expect(new URL(response.headers.get("x-middleware-rewrite") ?? "").pathname).toBe(
        `/ru${path}`,
      );
    },
  );
  it.each(["/new", "/en/new", "/en/join"])("preserves supported app route %s", (path) => {
    expect(proxy(request(path)).status).toBe(200);
  });
});

describe("an explicit locale prefix wins over Accept-Language", () => {
  const withLanguage = (path: string, language: string) =>
    new NextRequest(`http://localhost${path}`, {
      headers: { "accept-language": language },
    });

  it.each(["/ru/adventure", "/ru/w/AbCdEfGhIjKlMnOpQrStUv"])(
    "serves %s in place for an English browser that keeps no cookie",
    (path) => {
      const response = proxy(withLanguage(path, "en-US,en;q=0.9"));
      expect(response.status).toBe(200);
      expect(response.headers.get("location")).toBeNull();
      expect(response.cookies.get("NEXT_LOCALE")?.value).toBe("ru");
    },
  );
  it("serves /en/adventure in place for a Russian browser", () => {
    const response = proxy(withLanguage("/en/adventure", "ru-RU,ru;q=0.9"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });
  it.each(["/ru", "/ru/"])("keeps the redirect from bare %s to the landing", (path) => {
    const response = proxy(withLanguage(path, "en-US,en;q=0.9"));
    expect(response.status).toBe(307);
    expect(new URL(response.headers.get("location") ?? "").pathname).toBe("/");
  });
  it("sets no cookie on a background request", () => {
    const background = new NextRequest("http://localhost/ru/adventure", {
      headers: { "accept-language": "en-US", "sec-fetch-dest": "empty" },
    });
    expect(proxy(background).cookies.get("NEXT_LOCALE")).toBeUndefined();
  });
  it("sets no cookie when it already names the locale", () => {
    expect(
      proxy(request("/ru/adventure", "ru")).cookies.get("NEXT_LOCALE"),
    ).toBeUndefined();
  });
  it("ignores a client-sent locale header", () => {
    const forged = new NextRequest("http://localhost/ru/w/bad", {
      headers: { "x-next-intl-locale": "en" },
    });
    const forwarded = proxy(forged).headers.get(
      "x-middleware-request-x-next-intl-locale",
    );
    expect(forwarded).toBe("ru");
  });
  it.each(["/family", "/w/AbCdEfGhIjKlMnOpQrStUv"])(
    "serves unprefixed %s in the default locale without a cookie",
    (path) => {
      const response = proxy(withLanguage(path, "en-US,en;q=0.9"));
      expect(response.status).toBe(200);
      expect(response.headers.get("location")).toBeNull();
      expect(response.cookies.get("NEXT_LOCALE")).toBeUndefined();
    },
  );
  it("still sends an English browser from / to /en", () => {
    expect(proxy(withLanguage("/", "en-US,en;q=0.9")).headers.get("location")).toContain(
      "/en",
    );
  });
  it("honours a stored English choice on an unprefixed path", () => {
    expect(proxy(request("/family", "en")).headers.get("location")).toContain(
      "/en/family",
    );
  });
});
