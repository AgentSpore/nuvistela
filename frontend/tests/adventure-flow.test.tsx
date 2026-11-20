import { act, screen, waitFor, within } from "@testing-library/react";
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
  startAdventure: vi.fn(),
  markQuestDone: vi.fn(),
  retryChapter: vi.fn(),
}));
const a = vi.mocked(adv);

const quest: adv.Quest = {
  id: "q1",
  seq: 1,
  title: "Построить шалаш",
  description: "Соберите шалаш из подушек.",
  skill: "teamwork",
  source: "template",
  status: "open",
};
const chapter = (status: adv.ChapterStatus): adv.Chapter => ({
  id: "c1",
  seq: 1,
  status,
  title: status === "ready" ? "Шалаш" : null,
  body: status === "ready" ? "Стоит." : null,
});
const view = (chapters: adv.Chapter[], q: adv.Quest | null): adv.Adventure => ({
  world: null,
  quest: q,
  chapters,
});
const empty = view([], null);

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.mocked(api.getMe).mockResolvedValue(member());
});
afterEach(() => vi.useRealTimers());

describe("start", () => {
  it("an adult picks a genre and starts, then the screen reloads", async () => {
    a.getAdventure.mockResolvedValue(empty);
    a.startAdventure.mockResolvedValue({ world_status: "pending", quest });
    renderRu(<Adventure />);
    await userEvent.click(await screen.findByRole("radio", { name: "Космос" }));
    await userEvent.click(screen.getByRole("button", { name: "Начать" }));
    expect(a.startAdventure).toHaveBeenCalledWith("f1", "space");
    await waitFor(() => expect(a.getAdventure).toHaveBeenCalledTimes(3)); // initial, pre-start check, reload
  });

  it("a custom world needs its description", async () => {
    a.getAdventure.mockResolvedValue(empty);
    a.startAdventure.mockResolvedValue({ world_status: "pending", quest });
    renderRu(<Adventure />);
    expect(await screen.findByRole("button", { name: "Начать" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Опишите свой мир"), "Подводный город");
    await userEvent.click(screen.getByRole("button", { name: "Начать" }));
    expect(a.startAdventure).toHaveBeenCalledWith("f1", "custom", "Подводный город");
  });

  it("a child cannot start: no picker, a wait for the world", async () => {
    vi.mocked(api.getMe).mockResolvedValue(member({ role: "child", age_band: "6-9" }));
    a.getAdventure.mockResolvedValue(empty);
    renderRu(<Adventure />);
    expect(await screen.findByText(/выбирает ваш мир/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Начать" })).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
  });
});

describe("quest card", () => {
  it("is labelled as the current quest, visibly and by its accessible name", async () => {
    a.getAdventure.mockResolvedValue(view([], quest));
    renderRu(<Adventure />);
    const card = await screen.findByRole("region", { name: /Ваше задание/ });
    expect(within(card).getByText("Ваше задание")).toBeVisible();
    expect(within(card).getByText("Построить шалаш")).toBeInTheDocument();
  });

  it("a child can mark it done", async () => {
    vi.mocked(api.getMe).mockResolvedValue(member({ role: "child", age_band: "6-9" }));
    a.getAdventure.mockResolvedValue(view([], quest));
    renderRu(<Adventure />);
    expect(await screen.findByRole("button", { name: "Готово!" })).toBeEnabled();
  });
});

describe("done sheet", () => {
  const open = async () => {
    renderRu(<Adventure />);
    await userEvent.click(await screen.findByRole("button", { name: "Готово!" }));
  };

  it("counts the note characters", async () => {
    a.getAdventure.mockResolvedValue(view([], quest));
    await open();
    expect(screen.getByText("0 из 280")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Заметка/), "Готово");
    expect(screen.getByText("6 из 280")).toBeInTheDocument();
  });

  it("reuses one key on retry and clears it on success", async () => {
    a.getAdventure.mockResolvedValue(view([], quest));
    a.markQuestDone.mockRejectedValueOnce(new api.ApiError("network", 0));
    a.markQuestDone.mockResolvedValue({ chapter: { id: "c1", status: "queued" } });
    await open();
    await userEvent.type(screen.getByLabelText(/Заметка/), "Мы справились");
    const send = screen.getByRole("button", { name: "Отправить отметку" });
    await userEvent.click(send);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const stored = sessionStorage.getItem("idem:q1");
    expect(stored).toMatch(/\S/);
    await userEvent.click(send);
    await waitFor(() => expect(a.markQuestDone).toHaveBeenCalledTimes(2));
    const keys = a.markQuestDone.mock.calls.map((c) => c[2]);
    expect(keys[0]).toBe(stored);
    expect(keys[1]).toBe(stored);
    expect(a.markQuestDone).toHaveBeenLastCalledWith("q1", "Мы справились", stored);
    await waitFor(() => expect(sessionStorage.getItem("idem:q1")).toBeNull());
    expect(a.getAdventure).toHaveBeenCalledTimes(2);
  });
});

describe("done sheet as a modal", () => {
  const open = async () => {
    a.getAdventure.mockResolvedValue(view([], quest));
    renderRu(<Adventure />);
    const trigger = await screen.findByRole("button", { name: "Готово!" });
    await userEvent.click(trigger);
    return trigger;
  };

  it("is a named dialog; Escape closes it and focus returns to the trigger", async () => {
    const trigger = await open();
    expect(screen.getByRole("dialog", { name: "Задание выполнено?" })).toBeVisible();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("the close button also returns focus to the trigger", async () => {
    const trigger = await open();
    await userEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("two quick clicks on send make one request with one key", async () => {
    let finish: (v: Awaited<ReturnType<typeof adv.markQuestDone>>) => void = () => {};
    a.markQuestDone.mockImplementation(() => new Promise((r) => (finish = r)));
    await open();
    await userEvent.dblClick(screen.getByRole("button", { name: "Отправить отметку" }));
    expect(a.markQuestDone).toHaveBeenCalledTimes(1);
    finish({ chapter: { id: "c1", status: "queued" } });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("hung send", () => {
  it("times out into the normal error note and the buttons come back", async () => {
    const real = await vi.importActual<typeof adv>("@/lib/adventure-api");
    a.getAdventure.mockResolvedValue(view([], quest));
    a.markQuestDone.mockImplementation(real.markQuestDone);
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_, reject) =>
            init.signal?.addEventListener("abort", () => reject(new Error("aborted"))),
          ),
      ),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await userEvent.click(await screen.findByRole("button", { name: "Готово!" }));
    await userEvent.click(screen.getByRole("button", { name: "Отправить отметку" }));
    expect(screen.getByRole("button", { name: "Отправляем…" })).toBeDisabled();
    await act(() => vi.advanceTimersByTimeAsync(15_000));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Нет связи/);
    expect(screen.getByRole("button", { name: "Отправить отметку" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Закрыть" })).toBeEnabled();
    vi.unstubAllGlobals();
  });
});

describe("start response", () => {
  it("a null world_status is a success: the adventure shows, no error", async () => {
    const real = await vi.importActual<typeof adv>("@/lib/adventure-api");
    a.getAdventure.mockResolvedValueOnce(empty);
    a.getAdventure.mockResolvedValue(view([], quest));
    a.startAdventure.mockImplementation(real.startAdventure);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ world_status: null, quest }))),
    );
    renderRu(<Adventure />);
    await userEvent.click(await screen.findByRole("radio", { name: "Сказка" }));
    await userEvent.click(screen.getByRole("button", { name: "Начать" }));
    expect(await screen.findByText("Построить шалаш")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    vi.unstubAllGlobals();
  });
});

describe("retry note (a)", () => {
  it("is cleared once the chapter becomes ready", async () => {
    a.getAdventure.mockResolvedValueOnce(view([chapter("delayed_model")], quest));
    a.getAdventure.mockResolvedValueOnce(view([chapter("queued")], quest));
    a.getAdventure.mockResolvedValue(view([chapter("ready")], quest));
    a.retryChapter.mockRejectedValue(new api.ApiError("http", 409));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Попробовать снова" }),
    );
    expect(await screen.findByText(/уже в работе/)).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(3000));
    await screen.findByRole("heading", { level: 3, name: "Шалаш" });
    expect(screen.queryByText(/уже в работе/)).toBeNull();
  });
});

describe("announcement (d)", () => {
  it("the one status line speaks a delayed card, the card itself stays quiet", async () => {
    a.getAdventure.mockResolvedValueOnce(view([chapter("queued")], quest));
    a.getAdventure.mockResolvedValue(view([chapter("delayed_model")], quest));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await screen.findByText("Глава ждёт своей очереди", { selector: "p.sr-only" });
    await act(() => vi.advanceTimersByTimeAsync(3000));
    const title = "Рассказчик сейчас недоступен";
    await screen.findAllByText(title);
    const live = screen.getAllByRole("status").filter((e) => e.textContent === title);
    expect(live).toHaveLength(1);
    expect(live[0]).toHaveClass("sr-only");
  });
});

describe("a world chosen by another adult", () => {
  const pending: adv.Adventure = {
    world: { status: "pending" },
    quest: null,
    chapters: [],
  };

  it("the open choice form follows the poll into the waiting screen without a reload", async () => {
    a.getAdventure.mockResolvedValueOnce(empty).mockResolvedValue(pending);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await screen.findByRole("radio", { name: "Космос" });
    await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByText(/Мир уже выбран/)).toBeNull();
  });

  it("tells a player who had started typing that the world was taken", async () => {
    a.getAdventure.mockResolvedValueOnce(empty).mockResolvedValue(pending);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await userEvent.type(await screen.findByLabelText("Опишите свой мир"), "Остров");
    await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(screen.getByText(/Мир уже выбран другим взрослым/)).toBeVisible();
  });

  it("a player who started the world is not told it was taken", async () => {
    a.getAdventure
      .mockResolvedValueOnce(empty)
      .mockResolvedValueOnce(empty)
      .mockResolvedValue(pending);
    a.getWorld.mockResolvedValue({
      status: "pending",
      genre: "custom",
      cover: null,
      world: null,
    });
    a.startAdventure.mockResolvedValue({ world_status: "pending", quest: null });
    renderRu(<Adventure />);
    await userEvent.type(await screen.findByLabelText("Опишите свой мир"), "Остров");
    await userEvent.click(screen.getByRole("button", { name: "Начать" }));
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(screen.queryByText(/Мир уже выбран/)).toBeNull();
    expect(screen.getByText("Остров")).toBeVisible();
  });
});

describe("a repeated choice", () => {
  const pending: adv.Adventure = {
    world: { status: "pending" },
    quest: null,
    chapters: [],
  };
  const KEY = "bumbli.worldChoice.f1";
  const OLD = JSON.stringify({ kind: "text", text: "Старый мир" });
  const storedWorld = (genre: string): adv.WorldResponse => ({
    status: "pending",
    genre,
    cover: null,
    world: null,
  });
  const type = async () =>
    userEvent.type(await screen.findByLabelText("Опишите свой мир"), "Остров");
  const go = () => userEvent.click(screen.getByRole("button", { name: "Начать" }));

  it("a world that appeared before the click is not started again and is announced", async () => {
    a.getAdventure.mockResolvedValueOnce(empty).mockResolvedValue(pending);
    a.getWorld.mockResolvedValue(storedWorld("space"));
    renderRu(<Adventure />);
    sessionStorage.setItem(KEY, OLD);
    await type();
    await go();
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(a.startAdventure).not.toHaveBeenCalled();
    expect(screen.getByText(/Мир уже выбран другим взрослым/)).toBeVisible();
    expect(screen.queryByText("Остров")).toBeNull();
  });

  it("another genre in the stored world means the choice was overtaken", async () => {
    a.getAdventure
      .mockResolvedValueOnce(empty)
      .mockResolvedValueOnce(empty)
      .mockResolvedValue(pending);
    a.startAdventure.mockResolvedValue({ world_status: "pending", quest: null });
    a.getWorld.mockResolvedValue({
      status: "pending",
      genre: "space",
      cover: null,
      world: null,
    });
    renderRu(<Adventure />);
    sessionStorage.setItem(KEY, OLD);
    await userEvent.click(await screen.findByRole("radio", { name: "Пираты" }));
    await go();
    expect(await screen.findByText(/Мир уже выбран другим взрослым/)).toBeVisible();
    expect(sessionStorage.getItem("bumbli.worldChoice.f1")).toBeNull();
  });

  it("a failed start leaves no quote behind", async () => {
    a.getAdventure.mockResolvedValue(empty);
    a.startAdventure.mockRejectedValue(new api.ApiError("network", 0));
    renderRu(<Adventure />);
    sessionStorage.setItem(KEY, OLD);
    await type();
    await go();
    await screen.findByRole("alert");
    expect(sessionStorage.getItem("bumbli.worldChoice.f1")).toBeNull();
  });
});

describe("form poll after a failed start", () => {
  it("resumes once the start failed: another adult's world still takes over the form", async () => {
    const pending: adv.Adventure = {
      world: { status: "pending" },
      quest: null,
      chapters: [],
    };
    a.getAdventure
      .mockResolvedValueOnce(empty)
      .mockResolvedValueOnce(empty)
      .mockResolvedValue(pending);
    a.startAdventure.mockRejectedValueOnce(new api.ApiError("network", 0));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await userEvent.click(await screen.findByRole("radio", { name: "Космос" }));
    await userEvent.click(screen.getByRole("button", { name: "Начать" }));
    await screen.findByRole("alert");
    await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(await screen.findByText("Мир пишется")).toBeVisible();
  });
});

describe("a world that exists but whose genre cannot be read", () => {
  it("counts as taken: no POST, no quote, the notice shows", async () => {
    const pending: adv.Adventure = {
      world: { status: "pending" },
      quest: null,
      chapters: [],
    };
    a.getAdventure.mockResolvedValueOnce(empty).mockResolvedValue(pending);
    a.getWorld.mockRejectedValue(new api.ApiError("network", 0));
    sessionStorage.setItem("bumbli.worldChoice.f1", "{}");
    renderRu(<Adventure />);
    await userEvent.type(await screen.findByLabelText("Опишите свой мир"), "Остров");
    await userEvent.click(screen.getByRole("button", { name: "Начать" }));
    expect(await screen.findByText(/Мир уже выбран другим взрослым/)).toBeVisible();
    expect(a.startAdventure).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("bumbli.worldChoice.f1")).toBeNull();
  });
});

describe("polling the open form", () => {
  it("asks again only after the previous read settled, and keeps a slow answer", async () => {
    let settle: (v: adv.Adventure) => void = () => {};
    const slow = new Promise<adv.Adventure>((r) => (settle = r));
    a.getAdventure.mockResolvedValueOnce(empty).mockReturnValueOnce(slow);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await screen.findByRole("radio", { name: "Космос" });
    for (let i = 0; i < 4; i++) await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(a.getAdventure).toHaveBeenCalledTimes(2);
    a.getAdventure.mockResolvedValue({
      world: { status: "pending" },
      quest: null,
      chapters: [],
    });
    await act(async () =>
      settle({ world: { status: "pending" }, quest: null, chapters: [] }),
    );
    expect(await screen.findByText("Мир пишется")).toBeVisible();
  });
});

describe("a choice retried or raced", () => {
  const pending: adv.Adventure = {
    world: { status: "pending" },
    quest: null,
    chapters: [],
  };
  const world = (genre: string): adv.WorldResponse => ({
    status: "pending",
    genre,
    cover: null,
    world: null,
  });
  const type = async () =>
    userEvent.type(await screen.findByLabelText("Опишите свой мир"), "Остров");
  const go = () => userEvent.click(screen.getByRole("button", { name: "Начать" }));

  it("a world of the same genre already stored is ours: no second POST, quote kept", async () => {
    a.getAdventure.mockResolvedValueOnce(empty).mockResolvedValue(pending);
    a.getWorld.mockResolvedValue(world("custom"));
    renderRu(<Adventure />);
    await type();
    await go();
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(a.startAdventure).not.toHaveBeenCalled();
    expect(screen.queryByText(/Мир уже выбран/)).toBeNull();
    expect(screen.getByText("Остров")).toBeVisible();
  });

  it("an unreadable pre-start state does not block the start", async () => {
    a.getAdventure
      .mockResolvedValueOnce(empty)
      .mockRejectedValueOnce(new api.ApiError("network", 0))
      .mockResolvedValue(pending);
    a.getWorld.mockResolvedValue(world("custom"));
    a.startAdventure.mockResolvedValue({ world_status: "pending", quest: null });
    renderRu(<Adventure />);
    await type();
    await go();
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(a.startAdventure).toHaveBeenCalledWith("f1", "custom", "Остров");
    expect(screen.getByText("Остров")).toBeVisible();
  });

  it("the form's own poll waits while the start is running, so the quote survives", async () => {
    let storedGenre: (w: adv.WorldResponse) => void = () => {};
    a.getAdventure.mockResolvedValueOnce(empty).mockResolvedValueOnce(empty);
    a.getAdventure.mockResolvedValue(pending);
    a.startAdventure.mockResolvedValue({ world_status: "pending", quest: null });
    a.getWorld.mockReturnValue(new Promise((r) => (storedGenre = r)));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderRu(<Adventure />);
    await type();
    await go();
    await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(screen.queryByText("Мир пишется")).toBeNull();
    await act(async () => storedGenre(world("custom")));
    expect(await screen.findByText("Мир пишется")).toBeVisible();
    expect(screen.getByText("Остров")).toBeVisible();
  });
});
