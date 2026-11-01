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
