import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
vi.mock("@/lib/world-3d-viewer", () => ({
  startViewer: vi.fn(() => new Promise(() => {})),
}));

const quest: adv.Quest = {
  id: "q1",
  seq: 1,
  title: "Найти маяк",
  description: "Дойдите до маяка.",
  skill: "наблюдательность",
  source: "model",
  status: "open",
};
const chapter: adv.Chapter = {
  id: "c1",
  seq: 1,
  status: "ready",
  title: "Глава",
  body: "Текст.",
};
const world: adv.WorldView = {
  title: "Маяк дождливой гавани",
  setting: "Тихий городок у моря.",
  prologue: "Добро пожаловать в Дождливую гавань.",
  locations: [{ name: "Комната фонаря", description: "Под куполом ждёт лампа." }],
  heroes: [],
};
const URL = `/api/v1/media/${"a1".repeat(32)}.webp`;
const reply = (cover: unknown, scene: unknown = null) =>
  ({
    status: "ready",
    genre: "pirates",
    world,
    cover,
    scene,
  }) as unknown as adv.WorldResponse;
const show = (cover: unknown, chapters: adv.Chapter[] = [], scene: unknown = null) => {
  a.getAdventure.mockResolvedValue({ world: { status: "ready" }, quest, chapters });
  a.getWorld.mockResolvedValue(reply(cover, scene));
  renderRu(<Adventure />);
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMe).mockResolvedValue(member());
});
afterEach(() => vi.useRealTimers());

describe("world schema", () => {
  const base = { status: "ready", world: null };
  it.each([
    ["absent", {}, null],
    ["null", { cover: null }, null],
    [
      "pending",
      { cover: { status: "pending", url: null } },
      { status: "pending", url: null },
    ],
    ["ready", { cover: { status: "ready", url: URL } }, { status: "ready", url: URL }],
    [
      "failed",
      { cover: { status: "failed", url: null } },
      { status: "failed", url: null },
    ],
  ])("accepts cover %s", (_n, extra, want) => {
    expect(adv.worldSchema.parse({ ...base, ...extra }).cover).toEqual(want);
  });
  it.each([
    ["absolute other origin", `https://evil.example${URL}`],
    ["protocol-relative", `//evil.example${URL}`],
    ["wrong path", "/api/v1/media/abc.webp"],
    ["wrong extension", URL.replace(".webp", ".png")],
  ])("a ready cover with a %s url counts as no cover", (_n, url) => {
    expect(
      adv.worldSchema.parse({ ...base, cover: { status: "ready", url } }).cover,
    ).toBeNull();
  });
  it("treats a missing genre as custom", () => {
    expect(adv.worldSchema.parse(base).genre).toBe("custom");
  });
});

describe("cover on the card", () => {
  it.each([
    ["pending", { status: "pending", url: null }],
    ["failed", { status: "failed", url: null }],
  ])("%s: placeholder, story at once, no error text", async (_n, cover) => {
    show(cover);
    expect(await screen.findByText(/Добро пожаловать/)).toBeVisible();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByTestId("world-cover-placeholder")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(screen.queryByText(/ошиб|не удалось|failed/i)).toBeNull();
  });

  it("pending: a drawing note on a moving gradient, not empty shapes or a second title", async () => {
    show({ status: "pending", url: null });
    const box = await screen.findByTestId("world-cover-placeholder");
    expect(box).toHaveTextContent(/^Рисуем ваш мир…$/);
    expect(box.querySelector("svg")).toBeNull();
    expect(box.querySelector(".cover-drift")).not.toBeNull();
  });

  it("pending over the daily budget: says the picture comes later and the game is on, still drifting", async () => {
    show({ status: "pending", url: null, deferred: true });
    const box = await screen.findByTestId("world-cover-placeholder");
    expect(box).toHaveTextContent(/^Картинку дорисуем позже — игра уже идёт$/);
    expect(box.querySelector(".cover-drift")).not.toBeNull();
  });

  it.each([
    [false, true],
    [true, false],
  ])("pending (deferred=%s): re-fetches quietly = %s", async (deferred, polls) => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    show({ status: "pending", url: null, deferred });
    await screen.findByTestId("world-cover-placeholder");
    const before = a.getWorld.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(a.getWorld.mock.calls.length > before).toBe(polls);
  });

  it("failed: a still gradient with no text and no promise of a picture", async () => {
    show({ status: "failed", url: null });
    const box = await screen.findByTestId("world-cover-placeholder");
    expect(box).toHaveTextContent(/^$/);
    expect(box.querySelector(".cover-drift")).toBeNull();
  });

  it("keeps the gradient moving while a ready picture loads, stops it once shown", async () => {
    show({ status: "ready", url: URL });
    const img = await screen.findByRole("img");
    const box = screen.getByTestId("world-cover-placeholder");
    expect(box.querySelector(".cover-drift")).not.toBeNull();
    fireEvent.load(img);
    expect(box.querySelector(".cover-drift")).toBeNull();
  });

  it("null: no cover box at all, story at once", async () => {
    show(null);
    expect(await screen.findByText(/Добро пожаловать/)).toBeVisible();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByTestId("world-cover-placeholder")).toBeNull();
  });

  it("ready: img with alt and url", async () => {
    show({ status: "ready", url: URL });
    const img = await screen.findByRole("img", {
      name: "Обложка мира «Маяк дождливой гавани»",
    });
    expect(img).toHaveAttribute("src", URL);
    expect(img).toHaveAttribute("width");
    expect(img).toHaveAttribute("height");
  });

  it("falls back to the placeholder when the picture fails to load", async () => {
    show({ status: "ready", url: URL });
    fireEvent.error(await screen.findByRole("img"));
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByTestId("world-cover-placeholder")).toBeInTheDocument();
  });

  it("collapsed card still shows the cover", async () => {
    show({ status: "ready", url: URL }, [chapter]);
    expect(await screen.findByRole("img", { name: /Обложка мира/ })).toBeVisible();
  });

  // The 3D walk is the world's gift: on the picture itself, not only inside the folded «О мире».
  const coverBox = async () =>
    (await screen.findByRole("img", { name: /Обложка мира/ }))
      .parentElement as HTMLElement;

  const OWN_SCENE = {
    status: "ready",
    url: `/api/v1/media/${"d".repeat(64)}.spz`,
    panorama_url: `/api/v1/media/pano/${"d".repeat(64)}.webp`,
  };
  const WALK = /Пройтись по миру · (до )?\d+ МБ/;
  const CORNER_WALK = /Пройтись по миру в 3D, (до )?\d+ МБ/;

  it.each([
    ["no scene", null],
    ["a pending scene", { status: "pending" }],
  ])(
    "with %s the cover has no walk; the library one stays in «О мире»",
    async (_n, scene) => {
      show({ status: "ready", url: URL }, [chapter], scene);
      const box = await coverBox();
      expect(within(box).queryByRole("button", { name: WALK })).toBeNull();
      const about = screen.getByText("О мире").closest("details") as HTMLElement;
      expect(
        within(about).getByRole("button", { name: WALK, hidden: true }),
      ).toBeInTheDocument();
    },
  );

  it("puts the walk button on the cover, bottom right, and it opens the world", async () => {
    show({ status: "ready", url: URL }, [chapter], OWN_SCENE);
    const box = await coverBox();
    const walk = within(box).getByRole("button", { name: CORNER_WALK });
    expect(walk.parentElement).toHaveClass("absolute", "bottom-2", "right-2");
    expect(walk).toHaveTextContent(/^В 3D$/);
    expect(walk).not.toHaveTextContent(/МБ/);
    expect(screen.getByText("О мире").closest("details")).not.toHaveAttribute("open");
    await userEvent.click(walk);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("names every button on the adventure screen, the folded ones too", async () => {
    show({ status: "ready", url: URL }, [chapter], OWN_SCENE);
    await coverBox();
    const buttons = screen.getAllByRole("button", { hidden: true });
    expect(buttons.length).toBeGreaterThan(2);
    const bare = buttons.filter(
      (b) => !(b.getAttribute("aria-label") ?? b.textContent ?? "").trim(),
    );
    expect(bare.map((b) => b.className)).toEqual([]);
  });

  it("keeps the growth note clear of the walk button", async () => {
    show({ status: "ready", url: URL }, [chapter]);
    const box = await coverBox();
    expect(within(box).getByRole("status", { hidden: true })).toHaveClass(
      "top-2",
      "left-2",
    );
  });

  it("is at least 2:1 on a phone on a return visit, as before from md up", async () => {
    show({ status: "ready", url: URL }, [chapter]);
    const box = await coverBox();
    expect(box).toHaveClass("aspect-[2/1]", "md:aspect-[3/1]");
    expect(box).not.toHaveClass("aspect-[3/1]");
  });

  it("is 2:1 on a phone on the first visit so the quest text fits above the fold, 5:2 from md up", async () => {
    show({ status: "ready", url: URL });
    expect(await coverBox()).toHaveClass("aspect-[2/1]", "md:aspect-[5/2]");
  });
});

describe("cover polling", () => {
  const pending = { status: "pending", url: null };
  const ready = { status: "ready", url: URL };
  const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));

  it("re-fetches while pending, stops on ready, keeps details open", async () => {
    show(pending);
    await screen.findByText(/Добро пожаловать/);
    a.getWorld.mockResolvedValue(reply(ready));
    await tick(3_100);
    expect(await screen.findByRole("img")).toHaveAttribute("src", URL);
    const calls = a.getWorld.mock.calls.length;
    expect(calls).toBe(2);
    await tick(60_000);
    expect(a.getWorld).toHaveBeenCalledTimes(calls);
    expect(screen.getByText(/Добро пожаловать/)).toBeVisible();
  });

  it("stops on failed", async () => {
    show(pending);
    await screen.findByText(/Добро пожаловать/);
    a.getWorld.mockResolvedValue(reply({ status: "failed", url: null }));
    await tick(3_100);
    await tick(60_000);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
  });

  it("stops at the bound while still pending", async () => {
    show(pending);
    await screen.findByText(/Добро пожаловать/);
    await tick(150_000);
    const calls = a.getWorld.mock.calls.length;
    expect(calls).toBeGreaterThan(10);
    await tick(60_000);
    expect(a.getWorld).toHaveBeenCalledTimes(calls);
  });

  it("a re-fetch keeps the user's choice and the same card node", async () => {
    show(pending);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const about = await screen.findByText("О мире");
    await user.click(about);
    const mark = (): HTMLElement | null => screen.getByText("О мире").closest("details");
    expect(mark()).not.toHaveAttribute("open");
    mark()!.dataset.mark = "kept";
    a.getWorld.mockResolvedValue(reply(ready));
    await tick(3_100);
    expect(await screen.findByRole("img")).toBeInTheDocument();
    expect(mark()).not.toHaveAttribute("open");
    expect(mark()!.dataset.mark).toBe("kept");
  });

  const setHidden = (hidden: boolean) => {
    Object.defineProperty(document, "hidden", { configurable: true, value: hidden });
    document.dispatchEvent(new Event("visibilitychange"));
  };
  afterEach(() => setHidden(false));

  it("makes no fetch while the tab is hidden and resumes without burning the bound", async () => {
    show(pending);
    await screen.findByText(/Добро пожаловать/);
    setHidden(true);
    await tick(200_000);
    expect(a.getWorld).toHaveBeenCalledTimes(1);
    setHidden(false);
    await tick(5_100);
    expect(a.getWorld).toHaveBeenCalledTimes(2);
    await tick(60_000);
    expect(a.getWorld.mock.calls.length).toBeGreaterThan(10);
  });

  it("a failed re-fetch keeps the shown world and raises no alert", async () => {
    show(pending);
    await screen.findByText(/Добро пожаловать/);
    a.getWorld.mockRejectedValue(new Error("network"));
    await tick(10_000);
    expect(a.getWorld.mock.calls.length).toBeGreaterThan(2);
    expect(screen.getByText(/Добро пожаловать/)).toBeVisible();
    expect(screen.queryByText("Не удалось загрузить мир")).toBeNull();
    expect(screen.getByTestId("world-cover-placeholder")).toBeInTheDocument();
  });

  it("returning to the tab resumes a first fetch whose retry was pending", async () => {
    a.getAdventure.mockResolvedValue({ world: { status: "ready" }, quest, chapters: [] });
    a.getWorld.mockRejectedValueOnce(new Error("network")).mockResolvedValue(reply(null));
    renderRu(<Adventure />);
    await screen.findByText("Найти маяк");
    setHidden(true);
    await tick(500);
    setHidden(false);
    await tick(30_000);
    expect(await screen.findByText(/Добро пожаловать/)).toBeVisible();
    expect(screen.queryByText("Не удалось загрузить мир")).toBeNull();
  });

  it("still shows the failure alert when the first fetch keeps failing", async () => {
    a.getAdventure.mockResolvedValue({ world: { status: "ready" }, quest, chapters: [] });
    a.getWorld.mockRejectedValue(new Error("network"));
    renderRu(<Adventure />);
    await screen.findByText("Найти маяк");
    await tick(20_000);
    expect(await screen.findByText("Не удалось загрузить мир")).toBeVisible();
  });
});
