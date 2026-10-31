import { assertServableHostname } from "@/lib/hostname-guard";

export function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  try {
    assertServableHostname(process.env.HOSTNAME);
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  }
}
