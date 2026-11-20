import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import { AppNav } from "@/components/app-nav";
import { QuestCard } from "@/components/quest-card";
import * as api from "@/lib/api";
import * as adv from "@/lib/adventure-api";
import en from "../messages/en.json";
import es from "../messages/es.json";
import zh from "../messages/zh-CN.json";
import ru from "../messages/ru.json";
import { member, renderRu } from "./render";

const route = vi.hoisted(() => ({ path: "/adventure" }));
vi.mock("@/i18n/navigation", async (original) => ({
  ...(await original<typeof import("@/i18n/navigation")>()),
  usePathname: () => route.path,
}));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
  getWorld: vi.fn(),
  markQuestDone: vi.fn(),
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
  title: "Маяк дождливой гавани",
  setting: "Тихий городок у моря.",
  prologue: "Добро пожаловать в Дождливую гавань.",
  locations: [{ name: "Комната фонаря", description: "Под куполом ждёт лампа." }],
  heroes: [
    { member_id: "m1", hero_class: "Рисовальщик", trait: "терпеливый", skill: "Штрих" },
  ],
};
const chapter = (status: adv.ChapterStatus, seq = 1): adv.Chapter => ({
  id: `c${seq}`,
  seq,
  status,
  title: status === "ready" ? "Маяк найден" : null,
  body: status === "ready" ? "Текст главы." : null,
});
const view = (chapters: adv.Chapter[], q: adv.Quest | null): adv.Adventure => ({
  world: { status: "ready" },
  quest: q,
  chapters,
});

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.mocked(api.getMe).mockResolvedValue(member());
  a.getWorld.mockResolvedValue({ status: "ready", genre: "pirates", cover: null, world });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const follows = (first: Element, second: Element) =>
  Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("adventure screen order", () => {
  it("puts the title, then the quest, then the story, then the world details", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("ready")], quest));
    renderRu(<Adventure />);
    const title = await screen.findByRole("heading", {
      level: 2,
      name: /Маяк дождливой/,
    });
    const questCard = screen.getByRole("region", { name: /Ваше задание/ });
    const story = screen.getByRole("heading", { name: "Ваша история" });
    const about = screen.getByText("О мире").closest("details")!;
    expect(follows(title, questCard)).toBe(true);
    expect(follows(questCard, story)).toBe(true);
    expect(follows(story, about)).toBe(true);
    expect(about).toContainElement(screen.getByText(/Добро пожаловать/));
    expect(about).toContainElement(screen.getByText("Рисовальщик"));
  });

  it("collapses the world details once there are chapters", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("ready")], quest));
    renderRu(<Adventure />);
    const about = (await screen.findByText("О мире")).closest("details")!;
    expect(about).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText("О мире"));
    expect(about).toHaveAttribute("open");
  });

  it("keeps the world details open while there is no chapter yet", async () => {
    a.getAdventure.mockResolvedValue(view([], quest));
    renderRu(<Adventure />);
    const about = (await screen.findByText("О мире")).closest("details")!;
    expect(about).toHaveAttribute("open");
  });
});

describe.each([
  ["ru", ru, ["Игра", "Приключение", "Участники"], "Новая игра", "Ещё"],
  ["en", en, ["Play", "Adventure", "Players"], "New game", "More"],
  ["es", es, ["Jugar", "Aventura", "Jugadores"], "Nueva partida", "Más"],
  ["zh-CN", zh, ["游戏", "冒险", "玩家"], "新游戏", "更多"],
] as const)("nav (%s)", (locale, messages, tabs, fresh, more) => {
  const mount = () =>
    render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <AppNav />
      </NextIntlClientProvider>,
    );

  it("has three tabs in the row and no «new game» among them", () => {
    mount();
    const row = screen.getByRole("list");
    const names = within(row)
      .getAllByRole("link")
      .map((l) => l.textContent);
    expect(names.slice(0, 3)).toEqual(tabs);
    expect(names).not.toContain(fresh);
  });

  it("closes the menu on an outside tap, on Escape anywhere, and on its own link", async () => {
    mount();
    const toggle = screen.getByRole("button", { name: more });
    const link = () => screen.queryByRole("link", { name: fresh });
    const reopen = async () => {
      if (!link()) await userEvent.click(toggle);
      expect(link()).toBeInTheDocument();
    };
    expect(link()).toBeNull();
    await reopen();
    await userEvent.click(document.body);
    expect(link()).toBeNull();
    await reopen();
    await userEvent.keyboard("{Escape}");
    expect(link()).toBeNull();
    await reopen();
    await userEvent.click(link()!);
    expect(link()).toBeNull();
  });

  it("closes the menu when the route changes under it (back button, locale switch)", async () => {
    const view = mount();
    await userEvent.click(screen.getByRole("button", { name: more }));
    expect(screen.getByRole("link", { name: fresh })).toBeInTheDocument();
    route.path = "/play";
    view.rerender(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <AppNav />
      </NextIntlClientProvider>,
    );
    expect(screen.queryByRole("link", { name: fresh })).toBeNull();
    route.path = "/adventure";
  });

  it("keeps «new game» reachable in a menu", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: more }));
    expect(screen.getByRole("link", { name: fresh })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/new$/),
    );
  });
});

describe("chapter room", () => {
  it("reserves room for a pending chapter only", async () => {
    a.getAdventure.mockResolvedValue(
      view([chapter("queued", 2), chapter("delayed_model", 1)], null),
    );
    renderRu(<Adventure />);
    const queued = (await screen.findByText("Глава 2")).closest("li")!;
    const delayed = screen.getByText("Глава 1").closest("li")!;
    expect(queued.className).toContain("min-h-80");
    expect(delayed.className).not.toContain("min-h-80");
  });
});

describe("reward after «Готово!»", () => {
  const scrollIntoView = vi.fn();
  const reduced = (matches: boolean) =>
    vi.stubGlobal("matchMedia", (q: string) => ({ matches, media: q }));

  async function finishQuest() {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    a.markQuestDone.mockResolvedValue(undefined as never);
    a.getAdventure
      .mockResolvedValueOnce(view([], quest))
      .mockResolvedValueOnce(view([chapter("queued")], null))
      .mockResolvedValue(view([chapter("ready")], null));
    renderRu(<Adventure />);
    await user.click(await screen.findByRole("button", { name: "Готово!" }));
    await user.click(screen.getByRole("button", { name: "Отправить отметку" }));
  }

  const focus = vi.spyOn(HTMLElement.prototype, "focus");
  beforeEach(() => {
    focus.mockClear();
    scrollIntoView.mockClear();
    Element.prototype.scrollIntoView = scrollIntoView;
  });

  it("celebrates the quest and its skill, takes focus, and does not repeat the skeleton", async () => {
    reduced(false);
    await finishQuest();
    const card = await screen.findByRole("status", { name: "Найти маяк — выполнено" });
    expect(card).toHaveTextContent("наблюдательность");
    expect(card).toHaveTextContent("Пишем главу…");
    expect(card.querySelector(".skeleton")).toBeNull();
    expect(within(card).getByRole("heading")).toHaveFocus();
    expect(focus.mock.calls.at(-1)?.[0]).toEqual({ preventScroll: true });
    expect(screen.queryByRole("region", { name: /Ваше задание/ })).toBeNull();
    // still open: closing it now would shorten the page under the reader's scroll
    expect(screen.getByText("О мире").closest("details")).toHaveAttribute("open");
  });

  it("shows the world's reaction before the send is answered, then the usual lines", async () => {
    reduced(false);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let answer!: () => void;
    a.markQuestDone.mockReturnValue(
      new Promise((res) => (answer = () => res(undefined as never))),
    );
    a.getAdventure.mockResolvedValue(
      view([], { ...quest, reaction: "Маяк дрогнул и вспыхнул ярче." }),
    );
    renderRu(<Adventure />);
    await user.click(await screen.findByRole("button", { name: "Готово!" }));
    await user.click(screen.getByRole("button", { name: "Отправить отметку" }));
    const card = await screen.findByRole("status", { name: "Найти маяк — выполнено" });
    expect(card).toHaveTextContent("Маяк дрогнул и вспыхнул ярче.");
    expect(within(card).getByText("Мир откликается")).toHaveClass("sr-only");
    expect(card).toHaveTextContent("Пишем главу…");
    await act(async () => answer());
    expect(
      screen.getByRole("status", { name: "Найти маяк — выполнено" }),
    ).toBeInTheDocument();
  });

  it("takes the reaction back and reopens the sheet with the error when the send fails", async () => {
    reduced(false);
    const user = userEvent.setup();
    a.markQuestDone.mockRejectedValue(new Error("boom"));
    a.getAdventure.mockResolvedValue(view([], { ...quest, reaction: "Маяк вспыхнул." }));
    renderRu(<Adventure />);
    await user.click(await screen.findByRole("button", { name: "Готово!" }));
    await user.click(screen.getByRole("button", { name: "Отправить отметку" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status", { name: /выполнено/ })).toBeNull();
    expect(screen.getByRole("region", { name: /Ваше задание/ })).toBeVisible();
    expect(screen.getByRole("button", { name: "Отправить отметку" })).toBeEnabled();
    expect(screen.getByRole("dialog")).toContainElement(
      document.activeElement as HTMLElement,
    );
  });

  it("keeps the reopened sheet when the close from stepping aside arrives after a fast failure", async () => {
    reduced(false);
    const user = userEvent.setup();
    a.markQuestDone.mockRejectedValue(new Error("boom"));
    a.getAdventure.mockResolvedValue(view([], { ...quest, reaction: "Маяк вспыхнул." }));
    // A real dialog queues its close event; the shim fires it synchronously, hiding the order.
    const syncClose = HTMLDialogElement.prototype.close;
    HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
      this.removeAttribute("open");
      setTimeout(() => this.dispatchEvent(new Event("close")), 0);
    };
    try {
      renderRu(<Adventure />);
      await user.click(await screen.findByRole("button", { name: "Готово!" }));
      await user.click(screen.getByRole("button", { name: "Отправить отметку" }));
      await screen.findByRole("alert");
      await new Promise((r) => setTimeout(r, 50));
    } finally {
      HTMLDialogElement.prototype.close = syncClose;
    }
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("keeps the plain card when the quest has no reaction", async () => {
    reduced(false);
    await finishQuest();
    const card = await screen.findByRole("status", { name: "Найти маяк — выполнено" });
    expect(within(card).queryByText("Мир откликается")).toBeNull();
  });

  it("shows a pending chapter card, not an empty box, until the chapter exists", async () => {
    reduced(false);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    a.markQuestDone.mockResolvedValue(undefined as never);
    a.getAdventure.mockResolvedValue(view([], quest));
    renderRu(<Adventure />);
    await user.click(await screen.findByRole("button", { name: "Готово!" }));
    await user.click(screen.getByRole("button", { name: "Отправить отметку" }));
    const card = (await screen.findByText("Глава 1")).closest("li")!;
    expect(card).toHaveTextContent("Глава ждёт своей очереди");
    expect(card.querySelectorAll(".skeleton").length).toBeGreaterThanOrEqual(3);
  });

  it("scrolls softly to the arrived chapter and highlights it", async () => {
    reduced(false);
    await finishQuest();
    await screen.findByText("Пишем главу…");
    await act(() => vi.advanceTimersByTimeAsync(3_100));
    const fresh = (await screen.findByRole("heading", { name: "Маяк найден" })).closest(
      "li",
    )!;
    expect(screen.queryByText("Пишем главу…")).toBeNull();
    expect(fresh).toHaveAttribute("data-fresh", "true");
    expect(screen.getByText("О мире").closest("details")).not.toHaveAttribute("open");
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  it("does not animate the scroll under prefers-reduced-motion", async () => {
    reduced(true);
    await finishQuest();
    await screen.findByText("Пишем главу…");
    await act(() => vi.advanceTimersByTimeAsync(3_100));
    await screen.findByRole("heading", { name: "Маяк найден" });
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "auto", block: "start" });
  });

  it("neither scrolls nor highlights on a plain visit", async () => {
    reduced(false);
    a.getAdventure.mockResolvedValue(view([chapter("ready")], quest));
    renderRu(<Adventure />);
    const li = (await screen.findByRole("heading", { name: "Маяк найден" })).closest(
      "li",
    )!;
    expect(li).not.toHaveAttribute("data-fresh");
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});

describe("first chapter room", () => {
  const openSheet = async () => {
    await userEvent.click(await screen.findByRole("button", { name: "Готово!" }));
  };
  const room = () => document.querySelector(".min-h-80");

  it("is a plain hint until the check-in is sent, grows on send, and gives the room back on error", async () => {
    a.getAdventure.mockResolvedValue(view([], quest));
    let fail!: (e: unknown) => void;
    a.markQuestDone.mockReturnValue(new Promise((_, rej) => (fail = rej)));
    renderRu(<Adventure />);
    await openSheet();
    expect(
      screen.getByText("Первая глава появится, когда вы выполните задание."),
    ).toBeInTheDocument();
    expect(room()).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Отправить отметку" }));
    expect(room()).not.toBeNull();
    await act(async () => fail(new Error("boom")));
    expect(room()).toBeNull();
  });

  it("leaves «О мире» as the player left it when a chapter already exists", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("ready")], quest));
    a.markQuestDone.mockResolvedValue(undefined as never);
    renderRu(<Adventure />);
    const about = (await screen.findByText("О мире")).closest("details")!;
    expect(about).not.toHaveAttribute("open");
    await openSheet();
    await userEvent.click(screen.getByRole("button", { name: "Отправить отметку" }));
    await screen.findByRole("status", { name: /выполнено/ });
    expect(about).not.toHaveAttribute("open");
  });
});

describe("label separators follow the language", () => {
  const renderCard = (locale: string, messages: typeof zh) =>
    render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <QuestCard quest={quest} onDone={() => {}} />
      </NextIntlClientProvider>,
    );

  it("zh-CN quest card joins label and value with a full-width colon", () => {
    renderCard("zh-CN", zh);
    const line = screen.getByText(quest.skill).parentElement;
    expect(line?.textContent).toBe(`${zh.adventure.skill}：${quest.skill}`);
  });

  it("en quest card keeps the ASCII colon", () => {
    renderCard("en", en as typeof zh);
    expect(screen.getByText(quest.skill).parentElement?.textContent).toBe(
      `${en.adventure.skill}: ${quest.skill}`,
    );
  });
});
