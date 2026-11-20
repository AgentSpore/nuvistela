import { API_URL } from "@/lib/config";

/** Keep legacy page-view reporting while pilot reporting counts anonymous sessions separately. */
export function recordLandingView(locale: string): void {
  fetch(`${API_URL}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "landing_view", locale }),
    keepalive: true,
  }).catch(() => undefined);
}
