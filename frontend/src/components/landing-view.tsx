"use client";

import { useEffect } from "react";
import { recordLandingView } from "@/lib/waitlist";

let sent = false;

/** Reports one landing_view per page load; the module flag survives React remounts. */
export function LandingView({ locale }: { locale: string }) {
  useEffect(() => {
    if (sent) return;
    sent = true;
    recordLandingView(locale);
  }, [locale]);
  return null;
}
