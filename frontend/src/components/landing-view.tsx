"use client";

import { useEffect } from "react";
import { recordLandingView } from "@/lib/waitlist";
import { recordPilotEvent } from "@/lib/pilot-events";

let sent = false;

/** Reports one landing_view per page load; the module flag survives React remounts. */
export function LandingView({ locale }: { locale: string }) {
  useEffect(() => {
    if (sent) return;
    sent = true;
    recordLandingView(locale);
    void recordPilotEvent("landing_view", locale, null);
  }, [locale]);
  return null;
}
