"use client";
import { AppNav } from "@/components/app-nav";
import { usePathname } from "@/i18n/navigation";

/** App links on app routes; the landing never shows them and never asks the API for a session. */
export function HeaderNav() {
  return usePathname() === "/" ? null : <AppNav />;
}
