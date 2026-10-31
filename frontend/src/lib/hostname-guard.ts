const LOOPBACK = /^(127(\.\d{1,3}){3}|\[?::1\]?)$/;

/**
 * Next normalizes a 127.x/::1 request URL to `localhost` but compares rewrites against the
 * verbatim HOSTNAME, so next-intl's rewrite of `/` to `/ru` looks foreign, is proxied to itself and
 * `/ru` answers 307 `Location: /`. Fail at boot instead of looping in the browser.
 */
export function assertServableHostname(hostname: string | undefined): void {
  if (hostname && LOOPBACK.test(hostname)) {
    throw new Error(
      `HOSTNAME=${hostname} makes every default-locale page redirect to itself; use 0.0.0.0 or localhost`,
    );
  }
}
