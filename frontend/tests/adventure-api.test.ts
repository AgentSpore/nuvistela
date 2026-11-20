import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getAdventure,
  markQuestDone,
  retryChapter,
  startAdventure,
  WORLD_READ_TIMEOUT_MS,
  worldSchema,
} from "@/lib/adventure-api";

const ok = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
const fetchMock = vi.fn();

afterEach(() => fetchMock.mockReset());

describe("retryChapter", () => {
  it("accepts 202 and surfaces 409 as an http error", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(ok({ id: "c1", status: "queued" }, 202));
    await expect(retryChapter("c1")).resolves.toEqual({ id: "c1", status: "queued" });
    fetchMock.mockResolvedValueOnce(ok({}, 409));
    await expect(retryChapter("c1")).rejects.toMatchObject({ status: 409 });
    vi.unstubAllGlobals();
  });
});

describe("writes", () => {
  it("done sends the note and the Idempotency-Key header", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(ok({ chapter: { id: "c1", status: "queued" } }));
    await markQuestDone("q1", "Готово", "k-1");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toMatch(/\/quests\/q1\/done$/);
    expect(init.headers["Idempotency-Key"]).toBe("k-1");
    expect(JSON.parse(init.body)).toEqual({ note: "Готово" });
    vi.unstubAllGlobals();
  });

  it("start posts the genre and the custom text only for a custom world", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () =>
      ok({ world_status: "pending", quest: null }),
    );
    await startAdventure("f1", "space");
    await startAdventure("f1", "custom", "Подводный город");
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(init.body));
    expect(bodies).toEqual([
      { genre: "space" },
      { genre: "custom", custom_genre: "Подводный город" },
    ]);
    vi.unstubAllGlobals();
  });

  it("start accepts a null world_status", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async () => ok({ world_status: null, quest: null }));
    await expect(startAdventure("f1", "space")).resolves.toEqual({
      world_status: null,
      quest: null,
    });
    vi.unstubAllGlobals();
  });
});

describe("world scene", () => {
  const base = { status: "ready", genre: "pirates", world: null };
  const H = "a".repeat(64);
  const parse = (scene: unknown) => worldSchema.parse({ ...base, scene }).scene ?? null;

  it("keeps a ready scene served from our own media route", () => {
    const scene = {
      status: "ready",
      url: `/api/v1/media/${H}.spz`,
      panorama_url: `/api/v1/media/pano/${H}.webp`,
    };
    expect(parse(scene)).toEqual(scene);
  });

  it("keeps a pending scene so the screen can wait for it", () => {
    expect(parse({ status: "pending", url: null, panorama_url: null })).toEqual({
      status: "pending",
    });
  });

  it.each([
    ["absent", undefined],
    ["null", null],
    ["failed", { status: "failed", url: null, panorama_url: null }],
    [
      "another origin",
      {
        status: "ready",
        url: `https://evil.example/${H}.spz`,
        panorama_url: `/api/v1/media/pano/${H}.webp`,
      },
    ],
    [
      "a bad sha",
      {
        status: "ready",
        url: "/api/v1/media/zz.spz",
        panorama_url: `/api/v1/media/pano/${H}.webp`,
      },
    ],
  ])("counts %s as no scene", (_name, scene) => {
    expect(parse(scene)).toBeNull();
  });
});

describe("getAdventure read timeout", () => {
  const stalled = () =>
    fetchMock.mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_, reject) =>
          init.signal?.addEventListener("abort", () => reject(new Error("aborted"))),
        ),
    );

  it("a stalled read fails as a network error once a timeout is given", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
    stalled();
    const read = getAdventure("f1", WORLD_READ_TIMEOUT_MS);
    const settled = expect(read).rejects.toMatchObject({ kind: "network" });
    await vi.advanceTimersByTimeAsync(WORLD_READ_TIMEOUT_MS + 1);
    await settled;
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("without a timeout the read keeps waiting", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", fetchMock);
    stalled();
    let outcome = "pending";
    getAdventure("f1").then(
      () => (outcome = "ok"),
      () => (outcome = "failed"),
    );
    await vi.advanceTimersByTimeAsync(10 * WORLD_READ_TIMEOUT_MS);
    expect(outcome).toBe("pending");
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});
