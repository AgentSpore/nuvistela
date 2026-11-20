import { z } from "zod";
import { API_URL } from "@/lib/config";
import type { pilotAttribution } from "@/lib/pilot-events";

export const AGE_BANDS = ["3-5", "6-9", "10-13", "14-17", "adult"] as const;
export const ROLES = ["adult", "child"] as const;

export const memberResponseSchema = z.object({
  id: z.string(),
  family_id: z.string(),
  display_name: z.string(),
  age_band: z.enum(AGE_BANDS),
  role: z.enum(ROLES),
  interests: z.array(z.string()),
  is_owner: z.boolean(),
});
const inviteSchema = z.object({ member: memberResponseSchema, invite_url: z.string() });
const createdSchema = inviteSchema.extend({ family_id: z.string() });
const reissueSchema = z.object({ invite_url: z.string() });
const linkCodeSchema = z.object({
  code: z.string(),
  expires_at: z.string(),
  bot_username: z.string().nullable(),
});
const replySchema = z.object({ reply: z.string() });

export type Member = z.infer<typeof memberResponseSchema>;
export type Invite = z.infer<typeof inviteSchema>;
export type FamilyInput = {
  title: string;
  locale: string;
  privacy_consent: true;
  display_name: string;
  interests: string[];
  /** Anonymous first-touch pilot attribution; the server records the new game as a lead. */
  attribution?: ReturnType<typeof pilotAttribution>;
};
export type MemberInput = Omit<Member, "id" | "family_id" | "is_owner">;
export type LinkCode = z.infer<typeof linkCodeSchema>;

export class ApiError extends Error {
  constructor(
    readonly kind: "network" | "http" | "parse",
    readonly status: number,
    /** Machine code of an admission refusal (`rate_limited`, `daily_full`); absent otherwise. */
    readonly code?: string,
  ) {
    super(`${kind} ${status}`);
  }
}

function abortable(own: AbortSignal | null | undefined, timeoutMs?: number) {
  const abort = new AbortController();
  const timer = timeoutMs ? setTimeout(() => abort.abort(), timeoutMs) : undefined;
  const forward = () => abort.abort();
  if (own?.aborted) forward();
  own?.addEventListener("abort", forward, { once: true });
  const release = () => {
    clearTimeout(timer);
    own?.removeEventListener("abort", forward);
  };
  return { signal: abort.signal, release };
}

const refusalSchema = z.object({ detail: z.object({ code: z.string() }) });

async function refusalCode(res: Response): Promise<string | undefined> {
  const parsed = refusalSchema.safeParse(await res.json().catch(() => null));
  return parsed.success ? parsed.data.detail.code : undefined;
}

/** `timeoutMs` is opt-in: past it the request fails as a network error. None by default: the game master may take a minute. */
export async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  init?: RequestInit,
  timeoutMs?: number,
): Promise<z.infer<S>> {
  const { signal, release } = abortable(init?.signal, timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      ...init,
      signal,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
    if (!res.ok) throw new ApiError("http", res.status, await refusalCode(res));
    const parsed = schema.safeParse(await res.json().catch(() => null));
    if (!parsed.success) throw new ApiError("parse", res.status);
    return parsed.data;
  } catch (e) {
    throw e instanceof ApiError ? e : new ApiError("network", 0);
  } finally {
    release();
  }
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

/** The backend returns a root-relative invite path; the shareable link is on the page's origin. */
export const absoluteInvite = (path: string): string =>
  new URL(path, window.location.origin).href;

export const createFamily = (input: FamilyInput) =>
  request("/families", createdSchema, post(input));
export const deleteFamily = (familyId: string) =>
  request(`/families/${familyId}`, z.null(), { method: "DELETE" });
export const addMember = (familyId: string, input: MemberInput) =>
  request(`/families/${familyId}/members`, inviteSchema, post(input));
export const reissueInvite = (memberId: string) =>
  request(`/members/${memberId}/invite`, reissueSchema, post());
export const listMembers = (familyId: string) =>
  request(`/families/${familyId}/members`, z.array(memberResponseSchema));
export const acceptInvite = (token: string) =>
  request("/invite/accept", memberResponseSchema, post({ token }));
export const getMe = () => request("/me", memberResponseSchema);
export const issueTelegramCode = (familyId: string) =>
  request(`/families/${familyId}/telegram/link-code`, linkCodeSchema, post());
export const sendAgentMessage = (text: string) =>
  request("/agent/messages", replySchema, post({ text }));

/** The agent endpoint is not built yet: 404/501 mean "game master is coming". */
export const isAgentMissing = (e: unknown): boolean =>
  e instanceof ApiError && e.kind === "http" && (e.status === 404 || e.status === 501);
