import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import * as api from "@/lib/api";
import * as adv from "@/lib/adventure-api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
  getWorld: vi.fn(),
}));
const a = vi.mocked(adv);

const quest: adv.Quest = {
  id: "q1",
  seq: 1,
  title: "Найти маяк",
  description: "Дойдите до маяка.",
  skill: "наблюдательность",
  source: "model",
  status: "open",
};
const world: adv.WorldView = {
  title: "Космический дом",
  setting: "Тихо.",
  prologue: "Добро пожаловать домой.",
  locations: [],
  heroes: [],
};
const reply = (scene: unknown) =>
  ({
    status: "ready",
    genre: "space",
    world,
    cover: null,
    scene,
  }) as unknown as adv.WorldResponse;
const PENDING = { status: "pending" };
const READY = {
  status: "ready",
  url: `/api/v1/media/${"d".repeat(64)}.spz`,
  panorama_url: `/api/v1/media/pano/${"d".repeat(64)}.webp`,
};
const POLL = 20_000;
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
// "space" has no library world: the 3D button exists only once the family's own scene does.
const button = () =>
  screen.queryByRole("button", { name: /Пройтись по миру/, hidden: true });
const setHidden = (hidden: boolean) => {
  Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
  document.dispatchEvent(new Event("visibilitychange"));
};

async function show(first: unknown) {
  a.getAdventure.mockResolvedValue({ world: { status: "ready" }, quest, chapters: [] });
  a.getWorld.mockResolvedValue(reply(first));
  renderRu(<Adventure />);
  await screen.findByText(/Добро пожаловать домой/);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMe).mockResolvedValue(member());
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  setHidden(false);
  vi.useRealTimers();
});

describe("scene polling", () => {
  it("shows nothing while pending, then swaps to the own scene and stops", async () => {
    await show(PENDING);
    expect(button()).toBeNull();
    expect(document.body.textContent).not.toMatch(/строит|создаёт|генерир/i);
    a.getWorld.mockResolvedValue(reply(READY));
    await tick(POLL + 100);
    expect(button()).not.toBeNull();
    expect(a.getWorld).toHaveBeenCalledTimes(2);
    await tick(10 * POLL);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
  });

  it("stops on failed", async () => {
    await show(PENDING);
    a.getWorld.mockResolvedValue(
      reply({ status: "failed", url: null, panorama_url: null }),
    );
    await tick(POLL + 100);
    await tick(10 * POLL);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
    expect(button()).toBeNull();
  });

  it("makes no fetch while the tab is hidden and resumes when visible", async () => {
    await show(PENDING);
    setHidden(true);
    await tick(10 * POLL);
    expect(a.getWorld).toHaveBeenCalledTimes(1);
    setHidden(false);
    await tick(POLL + 100);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
  });

  it("stops at about 12 minutes while still pending", async () => {
    await show(PENDING);
    await tick(13 * 60_000);
    const calls = a.getWorld.mock.calls.length;
    expect(calls).toBeGreaterThan(30);
    expect(calls).toBeLessThanOrEqual(37);
    await tick(10 * 60_000);
    expect(a.getWorld).toHaveBeenCalledTimes(calls);
  });

  it("does not poll when there is no scene at all", async () => {
    await show(null);
    await tick(10 * POLL);
    expect(a.getWorld).toHaveBeenCalledTimes(1);
  });
});
