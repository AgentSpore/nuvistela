// Web Push only: no fetch handler, no caching, no offline.
function readPayload(event) {
  try {
    return event.data ? event.data.json() : {};
  } catch {
    return {};
  }
}

/** Same-origin target only: a payload must not send the reader elsewhere. */
function targetUrl(raw) {
  try {
    const url = new URL(raw || "/", self.location.origin);
    if (url.origin === self.location.origin) return url.href;
  } catch {
    // Not a URL: fall back to the start page.
  }
  return self.location.origin + "/";
}

/** Funnel signal `reminder_opened`; the kind only, best effort. */
function reportOpened(kind) {
  return fetch("/api/v1/push/opened", {
    method: "POST",
    credentials: "include",
    keepalive: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind }),
  }).catch(() => undefined);
}

async function openTarget(raw) {
  const href = targetUrl(raw);
  const open = await self.clients.matchAll({ type: "window" });
  const existing = open.find((c) => new URL(c.url).origin === self.location.origin);
  if (existing) {
    // A refused focus must not fall through to openWindow: it needs the same click allowance.
    await existing.focus().catch(() => undefined);
    try {
      await existing.navigate(href);
      return;
    } catch {
      // The tab cannot be navigated: open a new one.
    }
  }
  await self.clients.openWindow(href);
}

// Control the tab that enabled push, so a click can navigate it.
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  const { title, body, url, kind } = readPayload(event);
  event.waitUntil(
    self.registration.showNotification(title || "Nuvistela", {
      body,
      icon: "/icon-192.png",
      badge: "/badge-96.png",
      data: { url, kind },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const { url, kind } = event.notification.data ?? {};
  event.waitUntil(Promise.all([openTarget(url), reportOpened(kind)]));
});
