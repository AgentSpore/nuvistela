import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const fetchMock = vi.fn();
beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  history.replaceState(null, "", "/?source=share&email=private#secret");
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("anonymous pilot attribution", () => {
  it("persists first-touch source and UUID across reloads, excludes query/hash", async () => {
    const first = await import("@/lib/pilot-events");
    const original = first.pilotAttribution(null);
    history.replaceState(null, "", "/?source=newsletter");
    vi.resetModules();
    const next = await import("@/lib/pilot-events");
    expect(next.pilotAttribution("solo")).toEqual({ ...original, intent: "solo" });
    expect(original).toEqual({
      session_id: expect.stringMatching(/^[\da-f-]{36}$/),
      source: "share",
      intent: null,
    });
    expect(first.publicDemoUrl("es")).toBe(`${location.origin}/es?source=share#demo`);
    expect(first.publicDemoUrl("ru")).toBe(`${location.origin}/?source=share#demo`);
  });
  it.each(["x", "telegram", "substack", "youtube"])(
    "reads launch source %s from the address",
    async (source) => {
      history.replaceState(null, "", `/?source=${source}&utm_campaign=launch`);
      const { pilotAttribution } = await import("@/lib/pilot-events");
      expect(pilotAttribution(null).source).toBe(source);
    },
  );
  it("uses in-memory attribution when storage is denied and ignores unknown sources", async () => {
    history.replaceState(null, "", "/?source=private-value");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied");
    });
    const { pilotAttribution } = await import("@/lib/pilot-events");
    expect(pilotAttribution(null)).toEqual(pilotAttribution(null));
    expect(pilotAttribution(null).source).toBe("direct");
  });
});

describe("own checks and automation are not counted", () => {
  const okResponse = () => new Response(null, { status: 204 });
  const bodyOf = (call: number) => JSON.parse(fetchMock.mock.calls[call]?.[1].body);
  // Node's own `localStorage` global shadows jsdom's and throws without --localstorage-file.
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(navigator, "webdriver", { configurable: true, value: false });
  });

  it("?internal=1 stores the flag, marks events and attribution; ?internal=0 clears it", async () => {
    fetchMock.mockResolvedValue(okResponse());
    history.replaceState(null, "", "/?internal=1");
    const { recordPilotEvent, pilotAttribution } = await import("@/lib/pilot-events");
    await recordPilotEvent("landing_view", "en", null);
    expect(localStorage.getItem("nuvistela-internal")).toBe("1");
    expect(bodyOf(0).internal).toBe(true);
    history.replaceState(null, "", "/");
    vi.resetModules();
    const again = await import("@/lib/pilot-events");
    expect(again.pilotAttribution(null).internal).toBe(true);
    history.replaceState(null, "", "/?internal=0");
    vi.resetModules();
    const cleared = await import("@/lib/pilot-events");
    expect(cleared.pilotAttribution(null)).not.toHaveProperty("internal");
    expect(localStorage.getItem("nuvistela-internal")).toBeNull();
    expect(pilotAttribution).toBeTypeOf("function");
  });

  it("sends no pilot event when navigator.webdriver is set and flags the attribution", async () => {
    Object.defineProperty(navigator, "webdriver", { configurable: true, value: true });
    const { recordPilotEvent, pilotAttribution } = await import("@/lib/pilot-events");
    await recordPilotEvent("demo_start", "en", "solo");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(pilotAttribution("solo").internal).toBe(true);
  });
});

it.each([500, "network"])(
  "retries %s once with the same event_id and safe fields",
  async (failure) => {
    vi.useFakeTimers();
    if (typeof failure === "string")
      fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    else fetchMock.mockResolvedValueOnce(new Response(null, { status: failure }));
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const { recordPilotEvent } = await import("@/lib/pilot-events");
    const work = recordPilotEvent("demo_start", "en", "family");
    await vi.runAllTimersAsync();
    await work;
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const first = fetchMock.mock.calls[0];
    const second = fetchMock.mock.calls[1];
    expect(first?.[0]).toBe("/api/v1/pilot/events");
    expect(first?.[1].body).toBe(second?.[1].body);
    expect(Object.keys(JSON.parse(first?.[1].body)).sort()).toEqual([
      "event_id",
      "intent",
      "kind",
      "locale",
      "session_id",
      "source",
    ]);
  },
);
it.each([204, 409, 422])("does not retry HTTP %i", async (status) => {
  fetchMock.mockResolvedValue(new Response(null, { status }));
  const { recordPilotEvent } = await import("@/lib/pilot-events");
  await recordPilotEvent("share_click", "zh-CN", null);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("exhausts at most two failed sends without rejecting", async () => {
  vi.useFakeTimers();
  fetchMock.mockRejectedValue(new TypeError("offline"));
  const { recordPilotEvent } = await import("@/lib/pilot-events");
  const work = recordPilotEvent("demo_complete", "es", "solo");
  await vi.runAllTimersAsync();
  await expect(work).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

describe("share card visitors", () => {
  it("start a share-sourced session that the landing page then keeps", async () => {
    history.replaceState(null, "", "/ru/w/AbCdEfGhIjKlMnOpQrStUv");
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const first = await import("@/lib/pilot-events");
    await first.recordPilotEvent("share_viewed", "ru", null, "share");
    const sent = JSON.parse(fetchMock.mock.calls[0]?.[1].body);
    expect(sent).toMatchObject({ kind: "share_viewed", source: "share" });
    expect(JSON.stringify(sent)).not.toContain("AbCdEf");
    history.replaceState(null, "", "/?source=share#demo");
    vi.resetModules();
    const landing = await import("@/lib/pilot-events");
    expect(landing.pilotAttribution(null)).toMatchObject({
      session_id: sent.session_id,
      source: "share",
    });
  });
});
