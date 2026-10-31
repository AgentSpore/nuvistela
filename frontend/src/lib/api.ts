import { z } from "zod";
import { API_URL } from "@/lib/config";

export const AGE_BANDS = ["3-5", "6-9", "10-13", "14-17", "adult"] as const;
export const ROLES = ["adult", "child"] as const;

export const memberSchema = z.object({
  id: z.string(),
  family_id: z.string(),
  display_name: z.string(),
  age_band: z.enum(AGE_BANDS),
  role: z.enum(ROLES),
  interests: z.array(z.string()),
});
const inviteSchema = z.object({ member: memberSchema, invite_url: z.string() });
const createdSchema = inviteSchema.extend({ family_id: z.string() });
const reissueSchema = z.object({ invite_url: z.string() });
const replySchema = z.object({ reply: z.string() });

export type Member = z.infer<typeof memberSchema>;
export type AgeBand = (typeof AGE_BANDS)[number];
export type Role = (typeof ROLES)[number];
export type Invite = z.infer<typeof inviteSchema>;
export type FamilyCreated = z.infer<typeof createdSchema>;
export type FamilyInput = {
  title: string;
  locale: string;
  display_name: string;
  interests: string[];
};
export type MemberInput = Omit<Member, "id" | "family_id">;

export class ApiError extends Error {
  constructor(
    readonly kind: "network" | "http" | "parse",
    readonly status: number,
  ) {
    super(`${kind} ${status}`);
  }
}

async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    throw new ApiError("network", 0);
  }
  if (!res.ok) throw new ApiError("http", res.status);
  const parsed = schema.safeParse(await res.json().catch(() => null));
  if (!parsed.success) throw new ApiError("parse", res.status);
  return parsed.data;
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  body: body === undefined ? undefined : JSON.stringify(body),
});

/** Backend returns invite paths relative to its own origin. */
export const absoluteInvite = (path: string): string => new URL(path, API_URL).href;

export const createFamily = (input: FamilyInput) =>
  request("/families", createdSchema, post(input));
export const addMember = (familyId: string, input: MemberInput) =>
  request(`/families/${familyId}/members`, inviteSchema, post(input));
export const reissueInvite = (memberId: string) =>
  request(`/members/${memberId}/invite`, reissueSchema, post());
export const getMe = () => request("/me", memberSchema);
export const sendAgentMessage = (text: string) =>
  request("/agent/messages", replySchema, post({ text }));

/** The agent endpoint is not built yet: 404/501 mean "game master is coming". */
export const isAgentMissing = (e: unknown): boolean =>
  e instanceof ApiError && e.kind === "http" && (e.status === 404 || e.status === 501);
