import { act, screen, within } from "@testing-library/react";
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

const quest = {
  id: "q1",
  seq: 1,
  title: "Найти маяк",
  description: "Дойдите до маяка.",
  skill: "наблюдательность",
  source: "model" as const,
  status: "open" as const,
};
const world: adv.WorldView = {
  title: "Маяк дождливой гавани",
  setting: "Тихий городок у моря.",
  prologue: "Добро пожаловать в Дождливую гавань.",
  locations: [
    { name: "Комната фонаря", description: "Под стеклянным куполом ждёт лампа." },
    { name: "Колокол гавани", description: "Звонит сам, когда меняется прилив." },
  ],
  heroes: [
    {
      member_id: "m1",
      hero_class: "Рисовальщик дождя",
      trait: "терпеливый",
      skill: "Точный штрих",
    },
  ],
};
const view = (
  status: adv.WorldStatus,
  q: adv.Quest | null,
  chapters: adv.Chapter[] = [],
): adv.Adventure => ({ world: { status }, quest: q, chapters });
const chapter: adv.Chapter = {
  id: "c1",
  seq: 1,
  status: "ready",
  title: "Глава",
  body: "Текст.",
};

afterEach(() => vi.useRealTimers());

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMe).mockResolvedValue(member());
  a.getWorld.mockResolvedValue({ status: "ready", genre: "pirates", cover: null, world });
});

describe("world pending", () => {
  it("shows the waiting state, no start picker and no quest", async () => {
    a.getAdventure.mockResolvedValue(view("pending", null));
    renderRu(<Adventure />);
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(screen.getByText(/Страница обновится сама/)).toBeVisible();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("region", { name: /Ваше задание/ })).toBeNull();
    expect(a.getWorld).not.toHaveBeenCalled();
  });

  it("keeps an open quest below the waiting state", async () => {
    a.getAdventure.mockResolvedValue(view("pending", quest));
    renderRu(<Adventure />);
    expect(await screen.findByText("Найти маяк")).toBeInTheDocument();
    expect(screen.getByText("Мир пишется")).toBeVisible();
  });
});

describe.each(["ready", "fallback"] as const)("world %s", (status) => {
  it("reveals title, setting, prologue, places and the player's hero", async () => {
    a.getAdventure.mockResolvedValue(view(status, quest));
    renderRu(<Adventure />);
    const panel = (await screen.findByText("О мире")).closest("details")!;
    expect(panel).toHaveAttribute("open");
    const w = within(panel);
    expect(w.getByText("Добро пожаловать в Дождливую гавань.")).toBeVisible();
    expect(w.getByText("Тихий городок у моря.")).toBeVisible();
    expect(w.getByText("Рисовальщик дождя")).toBeVisible();
    expect(w.getByText("Колокол гавани")).not.toBeVisible();
    await userEvent.click(w.getByText(/Места · 2/));
    expect(w.getByText("Колокол гавани")).toBeVisible();
    expect(screen.getByText("Найти маяк")).toBeInTheDocument();
  });

  it("is collapsed on a return visit and opens on demand", async () => {
    a.getAdventure.mockResolvedValue(view(status, quest, [chapter]));
    renderRu(<Adventure />);
    const about = await screen.findByText("О мире");
    const panel = about.closest("details")!;
    expect(panel).not.toHaveAttribute("open");
    await userEvent.click(about);
    expect(panel).toHaveAttribute("open");
  });
});

it("never renders image prompts", async () => {
  a.getAdventure.mockResolvedValue(view("ready", quest));
  renderRu(<Adventure />);
  expect(await screen.findByText("Найти маяк")).toBeInTheDocument();
  expect(screen.queryByText(/illustration/i)).toBeNull();
});

it("orders headings: world title h2, places h3", async () => {
  a.getAdventure.mockResolvedValue(view("ready", quest));
  renderRu(<Adventure />);
  expect(
    await screen.findByRole("heading", { level: 2, name: /Маяк дождливой гавани/ }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { level: 3, name: "Места · 2" }),
  ).toBeInTheDocument();
});

it("hides the empty story while no quest is open and no chapter exists", async () => {
  a.getAdventure.mockResolvedValue(view("pending", null));
  renderRu(<Adventure />);
  expect(await screen.findByText("Мир пишется")).toBeVisible();
  expect(screen.queryByText("Ваша история")).toBeNull();
});

describe("world still loading", () => {
  it("holds the quest back until the world card is there, so nothing is pushed down", async () => {
    let release: (w: adv.WorldResponse) => void = () => {};
    a.getWorld.mockReturnValue(new Promise((resolve) => (release = resolve)));
    a.getAdventure.mockResolvedValue(view("ready", quest));
    renderRu(<Adventure />);
    await screen.findByRole("heading", { level: 1 });
    await act(async () => {});
    expect(screen.queryByText("Найти маяк")).toBeNull();
    await act(async () =>
      release({ status: "ready", genre: "pirates", cover: null, world }),
    );
    expect(await screen.findByText("Найти маяк")).toBeInTheDocument();
    expect(screen.getByText("Маяк дождливой гавани")).toBeInTheDocument();
  });
});

describe("world fetch failure", () => {
  it("retries with backoff, then offers an alert with a retry action", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    a.getWorld.mockRejectedValue(new Error("boom"));
    a.getAdventure.mockResolvedValue(view("ready", quest));
    renderRu(<Adventure />);
    expect(await screen.findByText("Найти маяк")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(20_000));
    expect(a.getWorld).toHaveBeenCalledTimes(4);
    expect(await screen.findByText("Не удалось загрузить мир")).toBeInTheDocument();
    a.getWorld.mockResolvedValue({
      status: "ready",
      genre: "pirates",
      cover: null,
      world,
    });
    await userEvent.click(screen.getByRole("button", { name: "Попробовать снова" }));
    expect(await screen.findByText("Маяк дождливой гавани")).toBeInTheDocument();
  });
});

it("shows the long-pending notice", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  a.getAdventure.mockResolvedValue(view("pending", null));
  renderRu(<Adventure />);
  expect(await screen.findByText("Мир пишется")).toBeVisible();
  expect(screen.queryByText(/дольше обычного/)).toBeNull();
  await act(() => vi.advanceTimersByTimeAsync(200_000));
  expect(await screen.findByText(/дольше обычного/)).toBeVisible();
});

describe("chapter long wait", () => {
  const notice = /Глава пишется дольше обычного/;
  const writing: adv.Chapter = { ...chapter, status: "writing", title: null, body: null };

  it("shows after 60 s of pending, honest about nothing being lost, clears when ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    a.getAdventure.mockResolvedValue(view("ready", quest, [writing]));
    renderRu(<Adventure />);
    expect(await screen.findByText(/Страница обновится сама/)).toBeVisible();
    await act(() => vi.advanceTimersByTimeAsync(50_000));
    expect(screen.queryByText(notice)).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(20_000));
    const card = (await screen.findByText("Глава 1")).closest("li")!;
    expect(within(card).getByText(notice)).toBeVisible();
    expect(within(card).getByText(/ничего не потеряется/)).toBeVisible();
    a.getAdventure.mockResolvedValue(view("ready", quest, [chapter]));
    await act(() => vi.advanceTimersByTimeAsync(16_000));
    expect(screen.queryByText(notice)).toBeNull();
    expect(screen.getByRole("heading", { level: 3, name: "Глава" })).toBeVisible();
  });

  it("sits on the older chapter, not the newest card, and is announced once", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const older = { ...writing, id: "c1", seq: 1 };
    a.getAdventure.mockResolvedValue(view("ready", quest, [older]));
    renderRu(<Adventure />);
    await screen.findByText(/Страница обновится сама/);
    await act(() => vi.advanceTimersByTimeAsync(65_000));
    a.getAdventure.mockResolvedValue(
      view("ready", quest, [older, { ...writing, id: "c2", seq: 2 }]),
    );
    await act(() => vi.advanceTimersByTimeAsync(6000));
    const older2 = screen.getByText("Глава 1").closest("li");
    const newer = screen.getByText("Глава 2").closest("li");
    expect(within(older2!).getByText(notice)).toBeVisible();
    expect(within(newer!).queryByText(notice)).toBeNull();
    expect(screen.getAllByText(notice)).toHaveLength(2);
  });

  it("names the slow chapter in the hidden line when the newest one is ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const older = { ...writing, id: "c1", seq: 1 };
    a.getAdventure.mockResolvedValue(view("ready", quest, [older]));
    renderRu(<Adventure />);
    await screen.findByText(/Страница обновится сама/);
    await act(() => vi.advanceTimersByTimeAsync(65_000));
    a.getAdventure.mockResolvedValue(
      view("ready", quest, [older, { ...chapter, id: "c2", seq: 2, title: "Новая" }]),
    );
    await act(() => vi.advanceTimersByTimeAsync(6000));
    const line = screen
      .getAllByRole("status")
      .find((n) => n.classList.contains("sr-only"));
    expect(line).toHaveTextContent(/^Новая\. Глава 1: Глава пишется дольше обычного/);
  });
});
