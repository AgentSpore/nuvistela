import { act, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorldPanel } from "@/components/world-panel";
import * as adv from "@/lib/adventure-api";
import ru from "../messages/ru.json";

vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getWorld: vi.fn(),
}));
const a = vi.mocked(adv);

const world: adv.WorldView = {
  title: "Маяк",
  setting: "Тихо.",
  prologue: "Добро пожаловать.",
  locations: [],
  heroes: [],
};
const OLD = `/api/v1/media/${"a1".repeat(32)}.webp`;
const NEW = `/api/v1/media/${"b2".repeat(32)}.webp`;
const reply = (url: string, growing: boolean, w: adv.WorldView = world) =>
  ({
    status: "ready",
    genre: "pirates",
    world: w,
    cover: { status: "ready", url },
    cover_growing: growing,
  }) as unknown as adv.WorldResponse;
const entry = (chapter: number) => ({ chapter, text: `Веха ${chapter}` });
const store = new Map<string, string>();

const panel = (chronicle: adv.ChronicleEntry[]) => (
  <NextIntlClientProvider locale="ru" messages={ru}>
    <WorldPanel
      familyId="f1"
      status="ready"
      memberId="m1"
      firstVisit={false}
      slow={false}
      chronicle={chronicle}
    />
  </NextIntlClientProvider>
);
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const cover = () => screen.queryByRole("img", { name: /Обложка/ });
const grown = () => screen.queryByText("Мир вырос");
const setHidden = (hidden: boolean) => {
  Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
  document.dispatchEvent(new Event("visibilitychange"));
};
const changing = () => screen.queryByText("Мир меняется…");

beforeEach(() => {
  vi.clearAllMocks();
  store.clear();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  });
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  setHidden(false);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("world schema", () => {
  const base = { status: "ready", world: null };
  it.each([
    ["absent", {}, false],
    ["true", { cover_growing: true }, true],
    ["odd", { cover_growing: "yes" }, false],
  ])("cover_growing %s", (_n, extra, want) => {
    expect(adv.worldSchema.parse({ ...base, ...extra }).cover_growing ?? false).toBe(
      want,
    );
  });
});

describe("growth cover", () => {
  it("keeps polling while cover_growing, then swaps the cover once with a caption", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, true));
    render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    expect(cover()).toHaveAttribute("src", OLD);
    expect(changing()).not.toBeNull();
    expect(changing()).toHaveClass("motion-safe:animate-pulse");
    await tick(3100);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
    a.getWorld.mockResolvedValue(reply(NEW, false));
    await tick(5100);
    expect(cover()).toHaveAttribute("src", NEW);
    expect(grown()).not.toBeNull();
    expect(grown()).not.toHaveClass("motion-safe:animate-pulse");
    expect(changing()).toBeNull();
    const calls = a.getWorld.mock.calls.length;
    await tick(60_000);
    expect(a.getWorld).toHaveBeenCalledTimes(calls);
  });

  it("does not poll a settled cover", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, false));
    render(panel([]));
    await screen.findByRole("img", { name: /Обложка/ });
    await tick(60_000);
    expect(a.getWorld).toHaveBeenCalledTimes(1);
    expect(changing()).toBeNull();
    expect(grown()).toBeNull();
  });

  it("refetches the world once when a milestone arrives", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, false));
    const { rerender } = render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    expect(a.getWorld).toHaveBeenCalledTimes(1);
    a.getWorld.mockResolvedValue(reply(OLD, true));
    rerender(panel([entry(3), entry(6)]));
    await tick(50);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
    expect(changing()).not.toBeNull();
    rerender(panel([entry(3), entry(6)]));
    await tick(50);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
  });

  it("marks a cover changed since the last visit only once", async () => {
    store.set("nuvistela-cover-seen:f1:Маяк", OLD);
    a.getWorld.mockResolvedValue(reply(NEW, false));
    const first = render(panel([]));
    expect(await screen.findByText("Мир вырос")).toBeVisible();
    first.unmount();
    render(panel([]));
    await screen.findByRole("img", { name: /Обложка/ });
    expect(grown()).toBeNull();
  });

  it("does not mark the very first cover", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, false));
    render(panel([]));
    await screen.findByRole("img", { name: /Обложка/ });
    expect(grown()).toBeNull();
  });

  it("keeps the shown world when the milestone refetch fails every time", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, false));
    const { rerender } = render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    a.getWorld.mockRejectedValue(new Error("down"));
    rerender(panel([entry(3), entry(6)]));
    await tick(60_000);
    expect(a.getWorld.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("heading", { name: /Маяк/ })).toBeVisible();
    expect(screen.queryByText(/Не удалось/)).toBeNull();
  });

  it("a regenerated world's first cover is not growth", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, false));
    const first = render(panel([]));
    await screen.findByRole("img", { name: /Обложка/ });
    first.unmount();
    a.getWorld.mockResolvedValue(reply(NEW, false, { ...world, title: "Новый мир" }));
    render(panel([]));
    await screen.findByRole("heading", { name: /Новый мир/ });
    expect(cover()).toHaveAttribute("src", NEW);
    expect(grown()).toBeNull();
  });

  it("drops the hint once the poll budget is spent", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, true));
    render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    expect(changing()).not.toBeNull();
    await tick(200_000);
    expect(changing()).toBeNull();
  });

  it("retries a failed milestone refetch so a growth in progress still lands", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, true));
    const { rerender } = render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    a.getWorld.mockRejectedValueOnce(new Error("down"));
    a.getWorld.mockResolvedValue(reply(NEW, false));
    rerender(panel([entry(3), entry(6)]));
    await tick(30_000);
    expect(cover()).toHaveAttribute("src", NEW);
    expect(grown()).not.toBeNull();
    expect(changing()).toBeNull();
  });

  it("keeps polling a growth in progress after the quiet retries run out", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, true));
    const { rerender } = render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    for (let i = 0; i < 5; i++) a.getWorld.mockRejectedValueOnce(new Error("down"));
    a.getWorld.mockResolvedValue(reply(NEW, false));
    rerender(panel([entry(3), entry(6)]));
    await tick(120_000);
    expect(cover()).toHaveAttribute("src", NEW);
    expect(changing()).toBeNull();
  });

  it("resumes a retry that the tab being hidden cleared", async () => {
    a.getWorld.mockResolvedValue(reply(OLD, true));
    const { rerender } = render(panel([entry(3)]));
    await screen.findByRole("img", { name: /Обложка/ });
    a.getWorld.mockRejectedValueOnce(new Error("down"));
    a.getWorld.mockResolvedValue(reply(NEW, false));
    rerender(panel([entry(3), entry(6)]));
    await tick(1000);
    setHidden(true);
    await tick(10_000);
    expect(cover()).toHaveAttribute("src", OLD);
    setHidden(false);
    await tick(10_000);
    expect(cover()).toHaveAttribute("src", NEW);
  });
});
