"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getWorld,
  type Cover,
  type Scene,
  type WorldResponse,
  type WorldStatus,
  type WorldView,
} from "@/lib/adventure-api";
import { pollDelay } from "@/lib/use-adventure";

const MAX_RETRIES = 3;
/** Cover polls before giving up: about two minutes at the capped 5 s delay. */
const MAX_COVER_POLLS = 24;
/** A 3D scene takes minutes: one quiet re-fetch every 20 s, 12 minutes at most. */
const SCENE_POLL_MS = 20_000;
const MAX_SCENE_POLLS = 36;

type WorldData = {
  world: WorldView | null;
  genre: string;
  cover: Cover | null;
  /** A growth cover is being made: `cover` is still the old picture. */
  growing: boolean;
  scene: Scene | null;
};

/** What a reply still waits for: a pending or growing cover, a pending scene. */
type Wants = { cover: boolean; scene: boolean };

type Handlers = {
  onData: (r: WorldData, wants: Wants) => void;
  onGaveUp: () => void;
  /** Every failed first-fetch attempt, before the retries run out. */
  onFailed: () => void;
};

/** Quiet re-fetch schedule: the cover backs off to 5 s for ~2 min, a scene waits 20 s for 12 min. */
function pollPlan() {
  let cover = false;
  let scene = false;
  let coverPolls = 0;
  let scenePolls = 0;
  return {
    want(coverPending: boolean, scenePending: boolean) {
      cover = coverPending;
      scene = scenePending;
    },
    /** The cover poll budget is spent: a growth cover is no longer being waited for. */
    coverSpent: () => coverPolls >= MAX_COVER_POLLS,
    /** Delay before the next re-fetch, or null when nothing is pending or a bound is reached. */
    next(): number | null {
      if (cover && coverPolls < MAX_COVER_POLLS) return pollDelay(coverPolls++);
      if (scene && scenePolls < MAX_SCENE_POLLS) {
        scenePolls++;
        return SCENE_POLL_MS;
      }
      return null;
    },
  };
}

type Plan = ReturnType<typeof pollPlan>;

/** Records what the reply still waits for and hands the world to the screen. */
function deliver(r: WorldResponse, plan: Plan, onData: Handlers["onData"]) {
  const wants = {
    // A cover deferred to tomorrow's budget is not polled: nothing changes before the reset.
    cover:
      (r.cover?.status === "pending" && r.cover.deferred !== true) ||
      r.cover_growing === true,
    scene: r.scene?.status === "pending",
  };
  plan.want(wants.cover, wants.scene);
  onData(
    {
      world: r.world,
      genre: r.genre,
      cover: r.cover,
      growing: r.cover_growing === true && !plan.coverSpent(),
      scene: r.scene?.status === "ready" ? r.scene : null,
    },
    wants,
  );
}

/**
 * Fetches the world: a failed first fetch is retried with the poll backoff, then `onGaveUp`.
 * While the cover is pending it re-fetches quietly, not while the tab is hidden. A failed re-fetch of a
 * world already shown is retried the same way but never reaches `onFailed`/`onGaveUp`. Returns the cleanup.
 */
function watchWorld(
  familyId: string,
  { onData, onGaveUp, onFailed }: Handlers,
  shown: Wants | null,
): () => void {
  let live = true;
  let timer: number | undefined;
  let loaded = shown !== null; // a world already on screen is never replaced by the failure alert
  let gaveUp = false;
  const plan = pollPlan();
  if (shown) plan.want(shown.cover, shown.scene); // what is on screen still being awaited survives the restart
  const arm = () => {
    window.clearTimeout(timer);
    const delay = live && !document.hidden ? plan.next() : null;
    if (delay !== null) timer = window.setTimeout(() => load(0), delay);
  };
  const load = (n: number) =>
    getWorld(familyId)
      .then((r) => {
        if (!live) return;
        loaded = true;
        deliver(r, plan, onData);
        arm();
      })
      .catch(() => {
        if (!live) return;
        if (!loaded) onFailed();
        if (n < MAX_RETRIES) timer = window.setTimeout(() => load(n + 1), pollDelay(n));
        else if (loaded) arm();
        else {
          gaveUp = true;
          onGaveUp();
        }
      });
  // Back on the tab: poll again; a world still unloaded is fetched afresh from attempt 0.
  const onVisibility = () => {
    if (document.hidden) return loaded && window.clearTimeout(timer);
    if (!loaded && !gaveUp) {
      window.clearTimeout(timer);
      load(0);
    } else arm();
  };
  document.addEventListener("visibilitychange", onVisibility);
  load(0);
  return () => {
    live = false;
    window.clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

/** The written world, fetched once its status turns ready and again when `milestones` grows (a new chronicle entry may have ordered a growth cover); `erred` is set at the first failed attempt, `failed` when the retries run out, `retry` starts over. `erred` outlives `retry` on purpose: once the screen has shown the quest without the world, a retry must not hide it again behind the placeholder (the world card then appears above it, a late shift the reader asked for by tapping retry). */
export function useWorld(
  familyId: string,
  status: WorldStatus,
  milestones = 0,
): WorldData & { failed: boolean; erred: boolean; retry: () => void } {
  const [data, setData] = useState<WorldData>({
    world: null,
    genre: "custom",
    cover: null,
    growing: false,
    scene: null,
  });
  const [failedFor, setFailedFor] = useState<string | null>(null);
  const [erredFor, setErredFor] = useState<string | null>(null);
  const key = `${familyId}:${status}`;
  const shown = useRef<{ familyId: string; wants: Wants } | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (status === "pending") return;
    return watchWorld(
      familyId,
      {
        onData: (r, wants) => {
          shown.current = { familyId, wants };
          setData(r);
        },
        onGaveUp: () => setFailedFor(key),
        onFailed: () => setErredFor(key),
      },
      shown.current?.familyId === familyId ? shown.current.wants : null,
    );
  }, [familyId, status, key, tick, milestones]);
  const retry = useCallback(() => {
    setFailedFor(null);
    setTick((n) => n + 1);
  }, []);
  return { ...data, failed: failedFor === key, erred: erredFor === key, retry };
}
