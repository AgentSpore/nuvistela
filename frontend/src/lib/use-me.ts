"use client";
import { useEffect, useState } from "react";
import { ApiError, getMe, type Member } from "@/lib/api";

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
