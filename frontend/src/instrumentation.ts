import { assertServableHostname } from "@/lib/hostname-guard";

export function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") assertServableHostname(process.env.HOSTNAME);
}
