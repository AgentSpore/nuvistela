"use client";
import { useCallback, useState } from "react";
import type { ChronicleEntry } from "@/lib/adventure-api";

const keyName = (familyId: string) => `nuvistela-milestones-seen:${familyId}`;

function readSeen(familyId: string): Set<number> {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(keyName(familyId)) ?? "[]");
    return new Set(Array.isArray(raw) ? raw.filter((n) => typeof n === "number") : []);
  } catch {
    return new Set();
  }
}

function writeSeen(familyId: string, seen: Set<number>) {
  try {
    localStorage.setItem(keyName(familyId), JSON.stringify([...seen]));
  } catch {
    // Storage is off: the highlight simply shows again next visit.
  }
}

/**
 * Chapters whose milestone this family had not seen when the screen opened. They stay marked for
 * as long as the screen is mounted. `observe` goes on the chronicle list: the chapters are
 * remembered once the list is actually on screen, so a card scrolled past unseen stays new.
 */
export function useFreshMilestones(familyId: string, chronicle: ChronicleEntry[]) {
  const [before] = useState(() => readSeen(familyId));
  const fresh: ReadonlySet<number> = new Set(
    chronicle.filter((e) => !before.has(e.chapter)).map((e) => e.chapter),
  );
  const observe = useCallback(
    (list: HTMLElement | null) => {
      if (!list) return;
      const remember = () => {
        const seen = readSeen(familyId); // not `before`: another tab may have added chapters
        chronicle.forEach((e) => seen.add(e.chapter));
        writeSeen(familyId, seen);
      };
      if (typeof IntersectionObserver === "undefined") return remember();
      const io = new IntersectionObserver(
        (hits) => hits.some((h) => h.isIntersecting) && remember(),
      );
      io.observe(list);
      return () => io.disconnect();
    },
    [familyId, chronicle],
  );
  return { fresh, observe };
}
