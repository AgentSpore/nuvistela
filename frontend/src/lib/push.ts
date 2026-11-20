import { API_URL } from "@/lib/config";

const DECLINED_KEY = "nuvistela-push-declined";
const SW_URL = "/sw.js";

export type EnableResult = "on" | "denied" | "taken" | "failed";
/** `taken`: the server says this device is subscribed by another member. */
export type SaveResult = "saved" | "taken" | "failed";

export const pushSupported = (): boolean =>
  typeof navigator !== "undefined" &&
  "serviceWorker" in navigator &&
  "PushManager" in window &&
  "Notification" in window;

/** iOS runs web push only for an app added to the Home Screen; in plain Safari `PushManager` is absent. */
export const needsHomeScreen = (): boolean =>
  typeof navigator !== "undefined" &&
  /iPad|iPhone|iPod/.test(navigator.userAgent) &&
  !("PushManager" in window);

export function wasDeclined(): boolean {
  try {
    return localStorage.getItem(DECLINED_KEY) === "1";
  } catch {
    return false;
  }
}

export function markDeclined(): void {
  try {
    localStorage.setItem(DECLINED_KEY, "1");
  } catch {
    // Storage is optional: the card may be offered again.
  }
}

/** The server's public VAPID key; null when the feature is off (404) or unreachable. */
export async function fetchPushKey(): Promise<string | null> {
  try {
    const res = await fetch(`${API_URL}/push/key`, { credentials: "include" });
    if (!res.ok) return null;
    const body: unknown = await res.json();
    const key =
      body && typeof body === "object" && "public_key" in body ? body.public_key : null;
    return typeof key === "string" && key ? key : null;
  } catch {
    return null;
  }
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration(SW_URL);
  return (await registration?.pushManager.getSubscription()) ?? null;
}

function keyBytes(base64Url: string): Uint8Array<ArrayBuffer> {
  const padded = base64Url.replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded.padEnd(Math.ceil(padded.length / 4) * 4, "="));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

const send = (method: "POST" | "DELETE", body: unknown) =>
  fetch(`${API_URL}/push/subscriptions`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/** Idempotent upsert of this device's subscription for the signed-in member. */
export async function saveSubscription(
  subscription: PushSubscription,
): Promise<SaveResult> {
  const { endpoint, keys } = subscription.toJSON();
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const res = await send("POST", { endpoint, keys, tz });
  if (res.ok) return "saved";
  return res.status === 409 ? "taken" : "failed";
}

/** On open: what the server holds for this member and this device. Null: nothing to save. */
export async function syncSubscription(): Promise<SaveResult | null> {
  try {
    const subscription = await currentSubscription();
    if (!subscription || Notification.permission !== "granted") return null;
    return await saveSubscription(subscription);
  } catch {
    return "failed";
  }
}

/** Call from a click handler only: the browser asks for permission here. */
export async function enablePush(publicKey: string): Promise<EnableResult> {
  try {
    if ((await Notification.requestPermission()) !== "granted") return "denied";
    await navigator.serviceWorker.register(SW_URL);
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey),
    });
    const saved = await saveSubscription(subscription);
    if (saved === "saved") return "on";
    // A taken subscription belongs to another member: leave it alone.
    if (saved === "taken") return "taken";
    await subscription.unsubscribe();
    return "failed";
  } catch {
    return "failed";
  }
}

/** Only for a device that is ON for this member: the server row is ours. */
export async function disablePush(): Promise<boolean> {
  try {
    const subscription = await currentSubscription();
    if (!subscription) return true;
    const removed = await send("DELETE", { endpoint: subscription.endpoint });
    if (!removed.ok) return false;
    // The server row is gone: that is the decision, a browser-side failure is not reported.
    await subscription.unsubscribe().catch(() => undefined);
    return true;
  } catch {
    return false;
  }
}
