import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

const source = readFileSync("public/sw.js", "utf8");
const ORIGIN = "https://nuvistela.test";

type Handler = (event: Record<string, unknown>) => void;

const fetchMock = vi.fn<typeof fetch>(async () => new Response(null, { status: 204 }));

type Tab = {
  url: string;
  focus?: () => Promise<void>;
  navigate?: (url: string) => Promise<unknown>;
};

function boot(open: Tab[]) {
  const handlers = new Map<string, Handler>();
  const shown: [string, NotificationOptions][] = [];
  const openWindow = vi.fn(async () => undefined);
  const claim = vi.fn(async () => undefined);
  const matchAll = vi.fn(async () => open);
  const scope = {
    location: { origin: ORIGIN },
    registration: {
      showNotification: async (title: string, options: NotificationOptions) => {
        shown.push([title, options]);
      },
    },
    clients: { matchAll, openWindow, claim },
    addEventListener: (type: string, fn: Handler) => handlers.set(type, fn),
  };
  new Function("self", "fetch", source)(scope, fetchMock);
  const dispatch = async (type: string, event: Record<string, unknown>) => {
    const waits: Promise<unknown>[] = [];
    handlers.get(type)?.({ ...event, waitUntil: (p: Promise<unknown>) => waits.push(p) });
    await Promise.all(waits);
  };
  return { handlers, shown, openWindow, claim, matchAll, dispatch };
}

const click = (url: unknown, kind = "chapter_ready") => ({
  notification: { close: vi.fn(), data: { url, kind } },
});

describe("service worker", () => {
  it("handles push and click only: no fetch handler, no caching", () => {
    expect([...boot([]).handlers.keys()].sort()).toEqual([
      "activate",
      "notificationclick",
      "push",
    ]);
    expect(source).not.toMatch(/caches|addEventListener\(["']fetch/);
  });

  it("claims open tabs on activate so the tab that enabled push is controlled", async () => {
    const sw = boot([]);
    await sw.dispatch("activate", {});
    expect(sw.claim).toHaveBeenCalledOnce();
  });

  it("shows the pushed title and body with the target url in data", async () => {
    const sw = boot([]);
    await sw.dispatch("push", {
      data: {
        json: () => ({
          title: "Маяк",
          body: "Новое задание",
          url: "/ru/adventure",
          kind: "chapter_ready",
        }),
      },
    });
    expect(sw.shown[0]?.[0]).toBe("Маяк");
    expect(sw.shown[0]?.[1]).toMatchObject({
      body: "Новое задание",
      data: { url: "/ru/adventure" },
    });
  });

  it("still shows a notification when the payload is not JSON", async () => {
    const sw = boot([]);
    await sw.dispatch("push", {
      data: {
        json: () => {
          throw new SyntaxError("bad");
        },
      },
    });
    expect(sw.shown[0]?.[0]).toBe("Nuvistela");
  });

  it("focuses a controlled tab of this origin first, then navigates it; never opens a window", async () => {
    const calls: string[] = [];
    const focus = vi.fn(async () => void calls.push("focus"));
    const navigate = vi.fn(async () => void calls.push("navigate"));
    const other = vi.fn(async () => undefined);
    const sw = boot([
      { url: "https://other.test/", focus, navigate: other },
      { url: `${ORIGIN}/ru/family`, focus, navigate },
    ]);
    const event = click("/ru/adventure");
    await sw.dispatch("notificationclick", event);
    expect(event.notification.close).toHaveBeenCalled();
    expect(calls).toEqual(["focus", "navigate"]);
    expect(navigate).toHaveBeenCalledWith(`${ORIGIN}/ru/adventure`);
    expect(other).not.toHaveBeenCalled();
    expect(sw.openWindow).not.toHaveBeenCalled();
    expect(sw.matchAll).toHaveBeenCalledWith({ type: "window" });
  });

  it("a failed focus never opens a window", async () => {
    const navigate = vi.fn(async () => undefined);
    const sw = boot([
      {
        url: `${ORIGIN}/`,
        focus: () => Promise.reject(new Error("no interaction allowance")),
        navigate,
      },
    ]);
    await sw.dispatch("notificationclick", click("/ru/adventure"));
    expect(navigate).toHaveBeenCalledWith(`${ORIGIN}/ru/adventure`);
    expect(sw.openWindow).not.toHaveBeenCalled();
  });

  it("opens a window when no tab is open, or navigate rejects", async () => {
    const none = boot([]);
    await none.dispatch("notificationclick", click("/ru/adventure"));
    expect(none.openWindow).toHaveBeenCalledWith(`${ORIGIN}/ru/adventure`);
    const stuck = boot([
      {
        url: `${ORIGIN}/`,
        focus: async () => undefined,
        navigate: () => Promise.reject(new Error("uncontrolled")),
      },
    ]);
    await stuck.dispatch("notificationclick", click("/ru/adventure"));
    expect(stuck.openWindow).toHaveBeenCalledWith(`${ORIGIN}/ru/adventure`);
  });

  it("uses the PNG icon and the monochrome badge for the notification", async () => {
    const sw = boot([]);
    await sw.dispatch("push", { data: { json: () => ({ title: "x" }) } });
    expect(sw.shown[0]?.[1]).toMatchObject({
      icon: "/icon-192.png",
      badge: "/badge-96.png",
    });
  });

  it("reports reminder_opened with the kind only, and a failed report does not block the open", async () => {
    fetchMock.mockClear();
    const sw = boot([]);
    await sw.dispatch("notificationclick", click("/ru/adventure", "quest_waiting"));
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/push/opened");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
    expect(JSON.parse(String(init?.body))).toEqual({ kind: "quest_waiting" });
    fetchMock.mockRejectedValueOnce(new Error("offline"));
    const down = boot([]);
    await down.dispatch("notificationclick", click("/ru/adventure"));
    expect(down.openWindow).toHaveBeenCalled();
  });

  it("never leaves the origin, whatever the payload says", async () => {
    const sw = boot([]);
    await sw.dispatch("notificationclick", click("https://evil.test/x"));
    expect(sw.openWindow).toHaveBeenCalledWith(`${ORIGIN}/`);
  });
});
