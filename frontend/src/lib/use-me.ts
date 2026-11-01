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

/** Family roster from the API; `reload` refetches after a member is added. */
export function useMembers(familyId: string): {
  members: Member[];
  failed: boolean;
  loaded: boolean;
  reload: () => void;
} {
  const [members, setMembers] = useState<Member[]>([]);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let ignore = false;
    listMembers(familyId).then(
      (list) => {
        if (ignore) return;
        setMembers(list);
        setLoaded(true);
        setFailed(false);
      },
      () => !ignore && setFailed(true),
    );
    return () => {
      ignore = true;
    };
  }, [familyId, tick]);
  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { members, failed, loaded, reload };
}
