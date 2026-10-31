const LOOPBACK = /^(127(\.\d{1,3}){3}|\[::1\])$/;

/**
 * Throws when `hostname` is a loopback address.
 *
 * Next normalizes a 127.x/::1 request URL to `localhost` but compares the middleware rewrite
 * against the verbatim HOSTNAME, so next-intl's rewrite of `/` to `/ru` looks foreign, is proxied
 * to itself and `/ru` answers 307 `Location: /`. The caller aborts boot instead of looping.
 *
 * Scope: standalone `server.js` only, the one entry point that binds to the HOSTNAME env.
 * `next start` and `next dev` bind with `-H` and ignore it, so they are neither guarded nor affected
 * by the env.
 */
export function assertServableHostname(hostname: string | undefined): void {
  if (!hostname) return;
  let normalized: string;
  try {
    const host = hostname.includes(":") && !hostname.startsWith("[") ? `[${hostname}]` : hostname;
    normalized = new URL(`http://${host}`).hostname;
  } catch {
    return;
  }
  if (LOOPBACK.test(normalized)) {
    throw new Error(
      `HOSTNAME=${hostname} makes every default-locale page redirect to itself; use 0.0.0.0 or localhost`,
    );
  }
}
