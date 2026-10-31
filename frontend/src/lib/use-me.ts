"use client";
import { useCallback, useEffect, useState } from "react";
import { ApiError, getMe, listMembers, type Member } from "@/lib/api";

export type MeState =
  | { status: "loading" }
  | { status: "ready"; me: Member }
  | { status: "anonymous" }
  | { status: "error" };

export function useMe(): MeState {
  const [state, setState] = useState<MeState>({ status: "loading" });
  useEffect(() => {
    getMe().then(
      (me) => setState({ status: "ready", me }),
      (e: unknown) =>
        setState(
          e instanceof ApiError && e.status === 401
            ? { status: "anonymous" }
            : { status: "error" },
        ),
    );
  }, []);
  return state;
}

export function errorKey(
  e: unknown,
): "network" | "unauthorized" | "forbidden" | "generic" {
  if (!(e instanceof ApiError)) return "generic";
  if (e.kind === "network") return "network";
  if (e.status === 401) return "unauthorized";
  if (e.status === 403) return "forbidden";
  return "generic";
}

/** Family roster from the API; `reload` refetches after a member is added. */
export function useMembers(familyId: string): { members: Member[]; reload: () => void } {
  const [members, setMembers] = useState<Member[]>([]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    listMembers(familyId).then(setMembers, () => setMembers([]));
  }, [familyId, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { members, reload };
}
