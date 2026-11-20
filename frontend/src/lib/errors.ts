import { ApiError, isAgentMissing } from "@/lib/api";

export type ErrorKey = "network" | "unauthorized" | "forbidden" | "generic";
export type AgentNote =
  | Exclude<ErrorKey, "generic">
  | "failed"
  | "soon"
  | "busy"
  | "limit"
  | "unavailable"
  | "textTooLong";

/** Message key under `errors.*` for a failed call. */
export function errorKey(e: unknown): ErrorKey {
  if (!(e instanceof ApiError)) return "generic";
  if (e.kind === "network") return "network";
  if (e.status === 401) return "unauthorized";
  if (e.status === 403) return "forbidden";
  return "generic";
}

const ADMISSION_KEYS: Record<string, "rateLimited" | "dailyFull"> = {
  rate_limited: "rateLimited",
  daily_full: "dailyFull",
};

/** Message key under `errors.*` when the server refuses a new game or invite right now. */
export function admissionKey(e: unknown): "rateLimited" | "dailyFull" | null {
  if (!(e instanceof ApiError) || e.status !== 429 || !e.code) return null;
  return ADMISSION_KEYS[e.code] ?? null;
}

const AGENT_STATUS: Record<number, AgentNote> = {
  409: "busy",
  422: "textTooLong",
  429: "limit",
  503: "unavailable",
};

/** Message key under `play.note.*` for a failed game master turn. */
export function agentNoteKey(e: unknown): AgentNote {
  if (isAgentMissing(e)) return "soon";
  if (e instanceof ApiError && e.kind === "http") {
    const mapped = AGENT_STATUS[e.status];
    if (mapped) return mapped;
  }
  const key = errorKey(e);
  return key === "generic" ? "failed" : key;
}
