import { z } from "zod";
import { GENRES } from "@/lib/adventure-api";
import { ApiError, request } from "@/lib/api";
import { API_URL } from "@/lib/config";

const LOCAL_BACKEND = "http://127.0.0.1:8080";
const TOKEN = /^[A-Za-z0-9_-]{22}$/;
const HOST = /^[a-z0-9.-]+(:\d{1,5})?$/i;

const cardSchema = z.object({
  title: z.string().nullable(),
  genre: z.enum(GENRES),
  cover_url: z.string().startsWith("/api/v1/share/"),
});
export type ShareData = z.infer<typeof cardSchema>;

const count = z.number().int().nonnegative();
const countsShape = { quests_done: count, chapters: count };
const publicSchema = cardSchema.extend(countsShape);
/** The public card plus the family's counters: numbers only, never names or chapter text. */
export type PublicShareData = z.infer<typeof publicSchema>;

/** The public card of a link, or null when it is gone, unknown or malformed (all one answer). */
export async function fetchShare(token: string): Promise<PublicShareData | null> {
  if (!TOKEN.test(token)) return null;
  const origin = process.env.API_ORIGIN ?? LOCAL_BACKEND;
  const response = await fetch(`${origin}/api/v1/share/${token}`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`share backend answered ${response.status}`);
  return publicSchema.parse(await response.json());
}

/** The origin the visitor (or the preview bot) used, from the proxy's headers; null if they look forged. */
export function requestOrigin(headers: Headers): string | null {
  const first = (name: string) => headers.get(name)?.split(",")[0]?.trim();
  const host = first("x-forwarded-host") ?? first("host");
  const proto = first("x-forwarded-proto") === "https" ? "https" : "http";
  return host && HOST.test(host) ? `${proto}://${host}` : null;
}

const createdSchema = z.object({ token: z.string().regex(TOKEN), created: z.boolean() });

/** Creates the family's link, or returns the active one again. 409: no ready cover or sharing off; 429: daily cap. */
export const createShare = (familyId: string) =>
  request(`/families/${familyId}/world/share`, createdSchema, { method: "POST" });

/** Turns off every link of the family (204, no body). */
export async function revokeShare(familyId: string): Promise<void> {
  const response = await fetch(`${API_URL}/families/${familyId}/world/share`, {
    method: "DELETE",
    credentials: "include",
  }).catch(() => {
    throw new ApiError("network", 0);
  });
  if (!response.ok) throw new ApiError("http", response.status);
}

const stateSchema = z.object({
  title: z.string().nullable(),
  genre: z.enum(GENRES),
  token: z.string().regex(TOKEN).nullable(),
  other_active: z.boolean(),
  ...countsShape,
});

/** What a link would show now (title vetted exactly like the public page) and the active link's token, if any. */
export const getShareState = (familyId: string) =>
  request(`/families/${familyId}/world/share`, stateSchema);
