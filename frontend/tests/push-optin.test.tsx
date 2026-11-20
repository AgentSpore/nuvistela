import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PushOptIn, PushToggle } from "@/components/push-optin";
import { renderRu } from "./render";

const ENDPOINT = "https://push.example/abc";
const subscription = {
  endpoint: ENDPOINT,
  toJSON: () => ({ endpoint: ENDPOINT, keys: { p256dh: "pk", auth: "ak" } }),
  unsubscribe: vi.fn(async () => true),
};

let permission: NotificationPermission;
let existing: typeof subscription | null;
let keyStatus: number;
let postStatus: number;
let fetchMock: ReturnType<typeof vi.fn>;
let order: string[];

beforeEach(() => {
  order = [];
  permission = "default";
  existing = null;
  keyStatus = 200;
  postStatus = 201;
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  });
  subscription.unsubscribe.mockClear();
  const pushManager = {
    getSubscription: async () => existing,
    subscribe: vi.fn(async () => {
      order.push("subscribe");
      return subscription;
    }),
  };
  const registration = { pushManager };
  vi.stubGlobal("PushManager", class {});
  vi.stubGlobal("Notification", {
    get permission() {
      return permission;
    },
    requestPermission: vi.fn(async () => {
      order.push("permission");
      permission = "granted";
      return permission;
    }),
  });
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      getRegistration: async () => (existing ? registration : undefined),
      register: async () => registration,
      ready: Promise.resolve(registration),
    },
  });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
    url.endsWith("/push/key")
      ? new Response(keyStatus === 200 ? JSON.stringify({ public_key: "BEl6" }) : null, {
          status: keyStatus,
        })
      : new Response(null, { status: init?.method === "POST" ? postStatus : 204 }),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

const calls = (method: string) =>
  fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === method,
  );

describe("push opt-in card", () => {
  it("asks permission only on the tap, then posts the subscription with the timezone", async () => {
    renderRu(<PushOptIn when />);
    const yes = await screen.findByRole("button", { name: "Да, сообщать" });
    expect(order).toEqual([]);
    await userEvent.click(yes);
    await waitFor(() => expect(calls("POST")).toHaveLength(1));
    expect(order).toEqual(["permission", "subscribe"]);
    expect(JSON.parse(String((calls("POST")[0]?.[1] as RequestInit).body))).toEqual({
      endpoint: ENDPOINT,
      keys: { p256dh: "pk", auth: "ak" },
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Да, сообщать" })).toBeNull(),
    );
  });

  it("«Не сейчас» is remembered on this device", async () => {
    const first = renderRu(<PushOptIn when />);
    await userEvent.click(await screen.findByRole("button", { name: "Не сейчас" }));
    expect(screen.queryByRole("heading")).toBeNull();
    first.unmount();
    renderRu(<PushOptIn when />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("a refused permission is never offered again", async () => {
    vi.mocked(Notification.requestPermission).mockImplementationOnce(
      async () => "denied",
    );
    renderRu(<PushOptIn when />);
    await userEvent.click(await screen.findByRole("button", { name: "Да, сообщать" }));
    await waitFor(() => expect(screen.queryByRole("heading")).toBeNull());
    expect(localStorage.getItem("nuvistela-push-declined")).toBe("1");
    expect(calls("POST")).toHaveLength(0);
  });

  it.each([
    ["the server has no key", () => (keyStatus = 404)],
    ["the browser has no push", () => vi.stubGlobal("PushManager", undefined)],
    ["already subscribed", () => ((existing = subscription), (permission = "granted"))],
    ["permission already denied", () => (permission = "denied")],
  ])("stays hidden when %s", async (_name, arrange) => {
    arrange();
    if (_name === "the browser has no push")
      delete (window as { PushManager?: unknown }).PushManager;
    renderRu(<PushOptIn when />);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("heading")).toBeNull();
  });
});

describe("push toggle", () => {
  it("shows the device state and switches it off with a DELETE", async () => {
    existing = subscription;
    permission = "granted";
    renderRu(<PushToggle />);
    const toggle = await screen.findByRole("switch");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
    expect(JSON.parse(String((calls("DELETE")[0]?.[1] as RequestInit).body))).toEqual({
      endpoint: ENDPOINT,
    });
    expect(subscription.unsubscribe).toHaveBeenCalled();
  });

  it("is hidden without a key and hints «Домой» on iOS Safari", async () => {
    keyStatus = 404;
    const first = renderRu(<PushToggle />);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("switch")).toBeNull();
    first.unmount();
    keyStatus = 200;
    delete (window as { PushManager?: unknown }).PushManager;
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
    );
    renderRu(<PushToggle />);
    expect(
      await screen.findByText(/Добавьте приложение на экран «Домой»/),
    ).toBeInTheDocument();
  });

  it("hides the iOS hint when the server has no key", async () => {
    keyStatus = 404;
    delete (window as { PushManager?: unknown }).PushManager;
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
    );
    renderRu(<PushToggle />);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText(/Добавьте приложение/)).toBeNull();
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("saves the local subscription for this member on mount before showing ON", async () => {
    existing = subscription;
    permission = "granted";
    renderRu(<PushToggle />);
    expect(await screen.findByRole("switch")).toHaveAttribute("aria-checked", "true");
    expect(calls("POST")).toHaveLength(1);
  });

  it("another family owns this device: OFF with a note, and turning on never unsubscribes", async () => {
    existing = subscription;
    permission = "granted";
    postStatus = 409;
    renderRu(<PushToggle />);
    const toggle = await screen.findByRole("switch");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(await screen.findByText(/другой семьи/)).toBeInTheDocument();
    await userEvent.click(toggle);
    await waitFor(() => expect(calls("POST")).toHaveLength(2));
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(subscription.unsubscribe).not.toHaveBeenCalled();
    expect(calls("DELETE")).toHaveLength(0);
  });

  it("a failing unsubscribe after the server DELETE still ends OFF without an error", async () => {
    existing = subscription;
    permission = "granted";
    subscription.unsubscribe.mockRejectedValueOnce(new Error("gone"));
    renderRu(<PushToggle />);
    const toggle = await screen.findByRole("switch");
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
    expect(screen.queryByText(/Не получилось/)).toBeNull();
  });
});

describe("push card mounting", () => {
  it("does not ask for the key when it cannot show", async () => {
    renderRu(<PushOptIn when={false} />);
    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not ask for the key after «Не сейчас»", async () => {
    localStorage.setItem("nuvistela-push-declined", "1");
    renderRu(<PushOptIn when />);
    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("push sync states", () => {
  it("a failed mount sync stays unknown: the failed note, no card", async () => {
    existing = subscription;
    permission = "granted";
    postStatus = 500;
    const toggle = renderRu(<PushToggle />);
    expect(await screen.findByText(/Не получилось/)).toBeInTheDocument();
    toggle.unmount();
    renderRu(<PushOptIn when />);
    await waitFor(() => expect(calls("POST")).toHaveLength(2));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("a device owned by another family is not offered the card", async () => {
    existing = subscription;
    permission = "granted";
    postStatus = 409;
    renderRu(<PushOptIn when />);
    await waitFor(() => expect(calls("POST")).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("heading")).toBeNull();
  });
});
