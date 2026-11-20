import { z } from "zod";
import { API_URL } from "@/lib/config";
import { shareCtaPath } from "@/lib/share-cta";

export type PilotIntent = "solo" | "family" | null;
type PilotEvent =
  | "landing_view"
  | "demo_start"
  | "demo_complete"
  | "cta_click"
  | "share_click"
  | "share_viewed"
  | "share_cta";
const SOURCES = [
  "direct",
  "share",
  "community",
  "newsletter",
  "x",
  "telegram",
  "substack",
  "youtube",
] as const;
type PilotSource = (typeof SOURCES)[number];
const sessionSchema = z.object({ session_id: z.uuid(), source: z.enum(SOURCES) });
const STORAGE_KEY = "bumbli-pilot-session";
const INTERNAL_KEY = "nuvistela-internal";
let session: z.infer<typeof sessionSchema> | undefined;

function pilotSession(fallback: PilotSource = "direct") {
  if (session) return session;
  try {
    const stored = sessionSchema.safeParse(
      JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? "null"),
    );
    if (stored.success) return (session = stored.data);
  } catch {
    // Storage is optional: private browsing can deny reads.
  }
  const source = new URLSearchParams(location.search).get("source");
  session = {
    session_id: crypto.randomUUID(),
    source: SOURCES.find((item) => item === source) ?? fallback,
  };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* Keep the same in-memory session when storage is unavailable. */
  }
  return session;
}

/** `?internal=1` marks this browser as the team's own; `?internal=0` clears the mark. */
function isInternal(): boolean {
  try {
    const flag = new URLSearchParams(location.search).get("internal");
    if (flag === "1") localStorage.setItem(INTERNAL_KEY, "1");
    if (flag === "0") localStorage.removeItem(INTERNAL_KEY);
    return localStorage.getItem(INTERNAL_KEY) === "1";
  } catch {
    return false;
  }
}

const isAutomated = () => navigator.webdriver === true;

/** First-touch attribution contains no URL, user text or contact details. */
export const pilotAttribution = (intent: PilotIntent, fallback?: PilotSource) => ({
  ...pilotSession(fallback),
  intent,
  ...(isInternal() || isAutomated() ? { internal: true } : {}),
});

/** A public localized root, never an invite, current query or private fragment. */
export function publicDemoUrl(locale: string): string {
  return new URL(shareCtaPath(locale), location.origin).href;
}

/**
 * Best-effort anonymous event; one bounded network/5xx retry uses the same event ID.
 * `fallback` is the source of a session this call starts when the URL names none (the share card).
 */
export async function recordPilotEvent(
  kind: PilotEvent,
  locale: string,
  intent: PilotIntent,
  fallback?: PilotSource,
): Promise<void> {
  if (isAutomated()) return;
  const body = JSON.stringify({
    event_id: crypto.randomUUID(),
    ...pilotAttribution(intent, fallback),
    kind,
    locale,
  });
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const response = await fetch(`${API_URL}/pilot/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        credentials: "omit",
        keepalive: true,
        signal: AbortSignal.timeout(2000),
      });
      if (response.status < 500) return;
    } catch {
      // Telemetry failures must not block the demo or signup.
    }
    if (attempt === 0) await new Promise((resolve) => setTimeout(resolve, 250));
  }
}
