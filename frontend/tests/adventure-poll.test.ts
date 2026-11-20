import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as adv from "@/lib/adventure-api";
import { POLL_MS, pollDelay, useAdventure } from "@/lib/use-adventure";

vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
}));
const get = vi.mocked(adv.getAdventure);
const withChapter = (status: adv.ChapterStatus): adv.Adventure => ({
  world: { status: "ready" },
  quest: null,
  chapters: [{ id: "c1", seq: 1, status, title: null, body: null }],
});
const hidden = (value: boolean) => {
  Object.defineProperty(document, "hidden", { value, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
};
const wait = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  hidden(false);
  vi.useRealTimers();
  get.mockReset();
});

const world = (status: adv.WorldStatus, quest: adv.Quest | null): adv.Adventure => ({
  world: { status },
  quest,
  chapters: [],
});
const quest: adv.Quest = {
  id: "q1",
  seq: 1,
  title: "T",
  description: "D",
  skill: "s",
  source: "model",
  status: "open",
};

describe("polling", () => {
  it("keeps the backoff for the world cover poll", () => {
    expect([0, 1, 2, 3, 9].map(pollDelay)).toEqual([3000, 4500, 5000, 5000, 5000]);
  });

  it("polls at a flat 1.5 s while a chapter is queued, however long it takes", async () => {
    expect(POLL_MS).toBe(1500);
    get.mockResolvedValue(withChapter("queued"));
    renderHook(() => useAdventure("f1"));
    await wait(0);
    for (let n = 2; n <= 8; n++) {
      await wait(1500);
      expect(get).toHaveBeenCalledTimes(n);
    }
  });

  it("keeps polling while writing, then stops once ready", async () => {
    get.mockResolvedValue(withChapter("writing"));
    renderHook(() => useAdventure("f1"));
    await wait(0);
    expect(get).toHaveBeenCalledTimes(1);
    await wait(1500);
    expect(get).toHaveBeenCalledTimes(2);
    get.mockResolvedValue(withChapter("ready"));
    await wait(1500);
    expect(get).toHaveBeenCalledTimes(3);
    await wait(120_000);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("stops while the tab is hidden and resumes when it is shown", async () => {
    get.mockResolvedValue(withChapter("queued"));
    renderHook(() => useAdventure("f1"));
    await wait(0);
    hidden(true);
    await wait(120_000);
    expect(get).toHaveBeenCalledTimes(1);
    hidden(false);
    await wait(0);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("does not re-arm when a slow reply lands after the tab was hidden", async () => {
    get.mockResolvedValueOnce(withChapter("queued"));
    renderHook(() => useAdventure("f1"));
    await wait(0);
    get.mockImplementation(
      () => new Promise((r) => setTimeout(() => r(withChapter("queued")), 2000)),
    );
    await wait(1500);
    hidden(true);
    await wait(120_000);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("does not poll when nothing is pending", async () => {
    get.mockResolvedValue(withChapter("delayed_model"));
    renderHook(() => useAdventure("f1"));
    await wait(120_000);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("stops after unmount", async () => {
    get.mockResolvedValue(withChapter("queued"));
    const { unmount } = renderHook(() => useAdventure("f1"));
    await wait(0);
    unmount();
    await wait(120_000);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("shows paused after a failed poll and clears it on the next good one", async () => {
    get.mockResolvedValueOnce(withChapter("queued"));
    const { result } = renderHook(() => useAdventure("f1"));
    await wait(0);
    expect(result.current.paused).toBe(false);
    get.mockRejectedValueOnce(new Error("offline"));
    await wait(1500);
    expect(result.current.paused).toBe(true);
    expect(result.current.state.status).toBe("ready");
    get.mockResolvedValue(withChapter("queued"));
    await wait(1500);
    expect(result.current.paused).toBe(false);
  });

  it("polls while the world is pending, then stops once ready with a quest", async () => {
    get.mockResolvedValue(world("pending", null));
    renderHook(() => useAdventure("f1"));
    await wait(0);
    get.mockResolvedValue(world("ready", quest));
    await wait(1500);
    expect(get).toHaveBeenCalledTimes(2);
    await wait(120_000);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("keeps polling when the world is ready but its first quest has not arrived", async () => {
    get.mockResolvedValue(world("ready", null));
    renderHook(() => useAdventure("f1"));
    await wait(0);
    await wait(1500);
    expect(get).toHaveBeenCalledTimes(2);
    await wait(1500);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it("turns slow after 3 minutes of continuous pending and clears when ready", async () => {
    get.mockResolvedValue(world("pending", null));
    const { result } = renderHook(() => useAdventure("f1"));
    await wait(0);
    expect(result.current.slow).toBe(false);
    await wait(170_000);
    expect(result.current.slow).toBe(false);
    await wait(30_000);
    expect(result.current.slow).toBe(true);
    get.mockResolvedValue(world("ready", quest));
    await wait(15_000);
    expect(result.current.slow).toBe(false);
  });

  it("times each chapter apart: slow after 60 s, cleared when ready, re-armed on a new wait", async () => {
    get.mockResolvedValue(withChapter("writing"));
    const { result } = renderHook(() => useAdventure("f1"));
    await wait(0);
    expect(result.current.slowChapterIds).toEqual([]);
    await wait(70_000);
    expect(result.current.slowChapterIds).toEqual(["c1"]);
    get.mockResolvedValue(withChapter("ready"));
    await wait(5000);
    expect(result.current.slowChapterIds).toEqual([]);
    get.mockResolvedValue(withChapter("queued"));
    act(() => result.current.reload());
    await wait(10_000);
    expect(result.current.slowChapterIds).toEqual([]);
    await wait(60_000);
    expect(result.current.slowChapterIds).toEqual(["c1"]);
  });

  it("flags only the chapter that has waited 60 s", async () => {
    const older: adv.Chapter = {
      id: "c1",
      seq: 1,
      status: "writing",
      title: null,
      body: null,
    };
    get.mockResolvedValue({ world: { status: "ready" }, quest: null, chapters: [older] });
    const { result } = renderHook(() => useAdventure("f1"));
    await wait(65_000);
    get.mockResolvedValue({
      world: { status: "ready" },
      quest: null,
      chapters: [older, { ...older, id: "c2", seq: 2 }],
    });
    await wait(10_000);
    expect(result.current.slowChapterIds).toEqual(["c1"]);
  });

  it("keeps the chapter and world clocks across a reload", async () => {
    get.mockResolvedValue(withChapter("writing"));
    const { result } = renderHook(() => useAdventure("f1"));
    await wait(65_000);
    expect(result.current.slowChapterIds).toEqual(["c1"]);
    act(() => result.current.reload());
    await wait(1000);
    expect(result.current.slowChapterIds).toEqual(["c1"]);
  });

  it("keeps the world clock across a reload", async () => {
    get.mockResolvedValue(world("pending", null));
    const { result } = renderHook(() => useAdventure("f1"));
    await wait(175_000);
    act(() => result.current.reload());
    await wait(10_000);
    expect(result.current.slow).toBe(true);
  });
});
