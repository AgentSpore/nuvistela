"use client";

import { useEffect } from "react";
import { recordPilotEvent } from "@/lib/pilot-events";

const VIEWED_PREFIX = "bumbli-share-viewed:";

/** A short non-reversible tag, so the link itself never sits in storage. */
function tag(token: string): string {
  let hash = 5381;
  for (const char of token) hash = (hash * 33) ^ char.charCodeAt(0);
  return (hash >>> 0).toString(36);
}

/** True the first time this browser session sees the link; true again when storage is denied. */
function firstViewThisSession(token: string): boolean {
  try {
    const key = VIEWED_PREFIX + tag(token);
    if (sessionStorage.getItem(key)) return false;
    sessionStorage.setItem(key, "1");
  } catch {
    // Storage is optional: count the view rather than lose it.
  }
  return true;
}

/**
 * Anonymous share-card accounting from the browser. Link previews from bots run no scripts, so
 * they are never counted. Events carry the locale only: no token, title or names.
 */
export function ShareBeacon({ token, locale }: { token: string; locale: string }) {
  useEffect(() => {
    if (firstViewThisSession(token)) {
      void recordPilotEvent("share_viewed", locale, null, "share");
    }
    const onClick = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest("a[data-share-cta]")) {
        void recordPilotEvent("share_cta", locale, null, "share");
      }
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [token, locale]);
  return null;
}
