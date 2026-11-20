import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "./i18n/routing";

const localize = createMiddleware(routing);

// next-intl 4.14.9 defaults for an unset routing.localeCookie: name NEXT_LOCALE, sameSite lax.
const LOCALE_COOKIE = "NEXT_LOCALE";

type Serving = { syncCookie: boolean; rewrite: boolean };

function serveDefaultLocale(request: NextRequest, { syncCookie, rewrite }: Serving) {
  // A client-sent header must not pick the locale: the URL prefix does.
  const headers = new Headers(request.headers);
  headers.set("x-next-intl-locale", routing.defaultLocale);
  const served = rewrite
    ? NextResponse.rewrite(
        new URL(
          `/${routing.defaultLocale}${request.nextUrl.pathname}${request.nextUrl.search}`,
          request.url,
        ),
        { request: { headers } },
      )
    : NextResponse.next({ request: { headers } });
  // Like next-intl's own cookie sync: documents only, not RSC fetches or prefetches.
  const dest = request.headers.get("sec-fetch-dest");
  const document = dest === null || dest === "document";
  if (
    syncCookie &&
    document &&
    request.cookies.get(LOCALE_COOKIE)?.value !== routing.defaultLocale
  ) {
    served.cookies.set(LOCALE_COOKIE, routing.defaultLocale, {
      path: "/",
      sameSite: "lax",
    });
  }
  return served;
}

/** Default-locale paths that skip next-intl's negotiation; undefined leaves them to it. */
function serveWithoutNegotiation(request: NextRequest) {
  // next-intl would redirect /ru/x to /x, and /x is then resolved from the cookie or
  // Accept-Language: without the cookie an English browser lands on /en/x. The prefix the
  // reader asked for decides, so deeper default-locale paths are served in place. Bare
  // /ru keeps next-intl's redirect: / stays the one landing URL.
  const [prefix, ...rest] = request.nextUrl.pathname.split("/").filter(Boolean);
  if (prefix === routing.defaultLocale && rest.length > 0)
    return serveDefaultLocale(request, { syncCookie: true, rewrite: false });
  // In-app links of the default locale are unprefixed (/family). Only / negotiates a
  // language; a deeper unprefixed path with no cookie is the default locale, or a reader
  // who left /ru/... would be switched to English by Accept-Language on the first click.
  const unprefixed =
    prefix !== undefined && !routing.locales.some((item) => item === prefix);
  if (unprefixed && !request.cookies.has(LOCALE_COOKIE))
    return serveDefaultLocale(request, { syncCookie: false, rewrite: true });
  return undefined;
}

export default function proxy(request: NextRequest) {
  return serveWithoutNegotiation(request) ?? localize(request);
}

export const config = { matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"] };
