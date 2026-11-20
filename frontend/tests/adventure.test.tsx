import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import * as api from "@/lib/api";
import * as adv from "@/lib/adventure-api";
import en from "../messages/en.json";
import ru from "../messages/ru.json";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
  retryChapter: vi.fn(),
}));
const a = vi.mocked(adv);

const quest = {
  id: "q1",
  seq: 2,
  title: "Построить шалаш",
  description: "Соберите шалаш из подушек.",
  skill: "teamwork",
  source: "template" as const,
  status: "open" as const,
};
const chapter = (status: adv.ChapterStatus, over: Partial<adv.Chapter> = {}) => ({
  id: "c1",
  seq: 1,
  status,
  title: null,
  body: null,
  ...over,
});
const view = (chapters: adv.Chapter[], q: adv.Quest | null = quest): adv.Adventure => ({
  world: { status: "ready" },
  quest: q,
  chapters,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMe).mockResolvedValue(member());
});

describe("chapter status", () => {
  it.each([
    ["queued", "Глава ждёт своей очереди"],
    ["writing", "Рассказчик пишет главу"],
    ["delayed_model", "Рассказчик сейчас недоступен"],
    ["delayed_budget", "На сегодня лимит историй исчерпан"],
  ] as const)("%s shows its own honest text", async (status, text) => {
    a.getAdventure.mockResolvedValue(view([chapter(status)]));
    renderRu(<Adventure />);
    const card = await screen.findByRole("listitem");
    expect(within(card).getByText(new RegExp(text))).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(new RegExp(text));
    expect(screen.queryByText("Глава готова")).not.toBeInTheDocument();
  });

  it("ready shows the written chapter, newest first", async () => {
    a.getAdventure.mockResolvedValue(
      view([
        chapter("ready", { title: "Лесная тропа", body: "Жили-были." }),
        chapter("ready", { id: "c2", seq: 2, title: "Шалаш", body: "Стоит." }),
      ]),
    );
    renderRu(<Adventure />);
    const titles = await screen.findAllByRole("heading", { level: 3 });
    expect(titles.map((h) => h.textContent)).toEqual(["Шалаш", "Лесная тропа"]);
    expect(screen.getByText("Жили-были.")).toBeInTheDocument();
  });

  it("delayed shows the quest the API returns", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("delayed_model")]));
    renderRu(<Adventure />);
    expect(await screen.findByText("Построить шалаш")).toBeInTheDocument();
  });
});

describe("retry", () => {
  it("adult retries a delayed chapter and the screen reloads", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("delayed_model")]));
    a.retryChapter.mockResolvedValue({ id: "c1", status: "queued" });
    renderRu(<Adventure />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Попробовать снова" }),
    );
    expect(a.retryChapter).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(a.getAdventure).toHaveBeenCalledTimes(2));
  });

  it("is hidden from a child", async () => {
    vi.mocked(api.getMe).mockResolvedValue(member({ role: "child", age_band: "6-9" }));
    a.getAdventure.mockResolvedValue(view([chapter("delayed_budget")]));
    renderRu(<Adventure />);
    const card = await screen.findByRole("listitem");
    expect(within(card).getByText(/лимит историй исчерпан/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Попробовать снова" })).toBeNull();
  });

  it("a rate limit is explained, not hidden", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("delayed_model")]));
    a.retryChapter.mockRejectedValue(new api.ApiError("http", 429));
    renderRu(<Adventure />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Попробовать снова" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/повторов уже много/);
  });
});

describe("retry failures", () => {
  it("a 409 note outlives the delayed card that the reload replaces", async () => {
    a.getAdventure.mockResolvedValueOnce(view([chapter("delayed_model")]));
    a.getAdventure.mockResolvedValue(view([chapter("queued")]));
    a.retryChapter.mockRejectedValue(new api.ApiError("http", 409));
    renderRu(<Adventure />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Попробовать снова" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/уже в работе/);
    expect(screen.queryByRole("button", { name: "Попробовать снова" })).toBeNull();
  });

  it("a 403 says only adults can do it", async () => {
    a.getAdventure.mockResolvedValue(view([chapter("delayed_model")]));
    a.retryChapter.mockRejectedValue(new api.ApiError("http", 403));
    renderRu(<Adventure />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Попробовать снова" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/только взрослым/);
  });
});

const TIME_PROMISE =
  /(?<![\p{L}])(завтра|час(?![\p{L}])|часа|часов|минут|tomorrow|hour|minute)/iu;

describe("delayed copy", () => {
  it("promises no day and no time, the worker retries by itself", () => {
    const text = JSON.stringify([ru.adventure, en.adventure]);
    expect(text).not.toMatch(TIME_PROMISE);
  });
});
