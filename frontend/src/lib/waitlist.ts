import { z } from "zod";
import { ApiError, request } from "@/lib/api";
import { API_URL } from "@/lib/config";

export const KIDS_BANDS = ["3-5", "6-9", "10-13", "14-17"] as const;
export type KidsBand = (typeof KIDS_BANDS)[number];
export type WaitlistInput = {
  email: string;
  family_size: number;
  kids_age_bands: KidsBand[];
  locale: string;
};
export type WaitlistErrorKey = "duplicate" | "invalid" | "limit" | "offline" | "generic";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
/** Same shape the backend accepts, so a typo is caught before the round trip. */
export const isEmail = (v: string): boolean => v.length <= 254 && EMAIL_RE.test(v);

export const joinWaitlist = (input: WaitlistInput) =>
  request("/waitlist", z.object({ ok: z.boolean() }), {
    method: "POST",
    body: JSON.stringify(input),
  });

const HTTP_KEYS: Record<number, WaitlistErrorKey> = {
  409: "duplicate",
  422: "invalid",
  429: "limit",
};

/** Message key under `waitlist.err.*` for a failed signup. */
export function waitlistErrorKey(e: unknown): WaitlistErrorKey {
  if (!(e instanceof ApiError)) return "generic";
  if (e.kind === "network") return "offline";
  return (e.kind === "http" && HTTP_KEYS[e.status]) || "generic";
}

/** Fire-and-forget funnel event; a failure must never reach the visitor. */
export function recordLandingView(locale: string): void {
  fetch(`${API_URL}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "landing_view", locale }),
    keepalive: true,
  }).catch(() => undefined);
}
