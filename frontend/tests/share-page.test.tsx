import { screen } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import en from "../messages/en.json";
import es from "../messages/es.json";
import zh from "../messages/zh-CN.json";
import ru from "../messages/ru.json";
import Page, { generateMetadata } from "@/app/[locale]/(card)/w/[token]/page";
import CardLayout from "@/app/[locale]/(card)/layout";
import { ShareUnavailable } from "@/components/share-card";
import { renderRu } from "./render";

const MESSAGES = { ru, en };
const TOKEN = "AbCdEfGhIjKlMnOpQrStUv";
const DEFAULT_HEADERS = {
  "x-forwarded-host": "nuvistela.example",
  "x-forwarded-proto": "https",
  host: "127.0.0.1:3000",
  cookie: "session=secret",
};
const state = vi.hoisted(() => ({ headers: new Headers() }));

vi.mock("next/headers", () => ({ headers: async () => state.headers }));
vi.mock("next-intl/server", () => ({
  setRequestLocale: () => undefined,
  getTranslations: async ({
    locale,
    namespace,
  }: {
    locale: "ru" | "en";
    namespace: "share" | "adventure.genre";
  }) => createTranslator({ locale, messages: MESSAGES[locale], namespace }),
}));

vi.mock("@/components/card-header", () => ({ CardHeader: () => <header>head</header> }));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const card = (title: string | null, genre = "pirates", quests_done = 0, chapters = 0) =>
  new Response(
    JSON.stringify({
      title,
      genre,
      cover_url: `/api/v1/share/${TOKEN}/cover.webp`,
      quests_done,
      chapters,
    }),
    { status: 200 },
  );
beforeEach(() => {
  fetchMock.mockReset();
  state.headers = new Headers(DEFAULT_HEADERS);
});
afterEach(() => vi.unstubAllEnvs());

const props = (locale: string, token = TOKEN) => ({
  params: Promise.resolve({ locale, token }),
});
const og = (m: Awaited<ReturnType<typeof generateMetadata>>) => m.openGraph;

describe("share page metadata", () => {
  it("carries the title and an absolute public cover address", async () => {
    fetchMock.mockResolvedValue(card("Тихая бухта"));
    const meta = await generateMetadata(props("ru"));
    expect(og(meta)?.title).toContain("Тихая бухта");
    expect(og(meta)?.description).toBeTruthy();
    expect(og(meta)?.images).toEqual([
      {
        url: `https://nuvistela.example/api/v1/share/${TOKEN}/cover.webp`,
        width: 1024,
        height: 687,
      },
    ]);
    expect(meta.twitter).toMatchObject({ card: "summary_large_image" });
    expect(meta.robots).toMatchObject({ index: false, follow: false });
  });

  it("falls back to the genre words when the title is null", async () => {
    fetchMock.mockResolvedValue(card(null, "space"));
    const meta = await generateMetadata(props("en"));
    expect(og(meta)?.title).toContain("Space");
  });

  it("asks the backend for the token only, without the visitor's cookies", async () => {
    fetchMock.mockResolvedValue(card("A"));
    await generateMetadata(props("en"));
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toMatch(new RegExp(`/api/v1/share/${TOKEN}$`));
    expect(new Headers(init?.headers).get("cookie")).toBeNull();
    expect(init?.credentials).toBeUndefined();
    expect(init).toEqual({ cache: "no-store" });
  });

  it.each([
    ["a path-like host", "evil.example/<x"],
    ["a host with a space", "a b"],
  ])("omits the image for %s", async (_name, host) => {
    state.headers = new Headers({ "x-forwarded-host": host });
    fetchMock.mockResolvedValue(card("A"));
    const meta = await generateMetadata(props("en"));
    expect(meta.openGraph?.images).toBeUndefined();
    expect(meta.twitter?.images).toBeUndefined();
  });

  it("takes the first of a forwarded host list", async () => {
    state.headers = new Headers({
      "x-forwarded-host": "a.example, b.example",
      "x-forwarded-proto": "https, http",
    });
    fetchMock.mockResolvedValue(card("A"));
    const meta = await generateMetadata(props("en"));
    expect(meta.openGraph?.images).toEqual([
      expect.objectContaining({
        url: `https://a.example/api/v1/share/${TOKEN}/cover.webp`,
      }),
    ]);
  });

  it("rejects a card whose cover points outside the public share path", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          title: "A",
          genre: "space",
          cover_url: "https://evil.example/x.webp",
        }),
        { status: 200 },
      ),
    );
    await expect(generateMetadata(props("en"))).rejects.toThrow();
  });

  it("is noindex without card data when the link is gone or malformed", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 404 }));
    const gone = await generateMetadata(props("ru"));
    expect(gone.robots).toMatchObject({ index: false, follow: false });
    expect(gone.openGraph?.images).toBeUndefined();
    const bad = await generateMetadata(props("ru", "../etc"));
    expect(bad.robots).toMatchObject({ index: false, follow: false });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("share page body", () => {
  it("answers 404 (notFound) for an unknown link", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 404 }));
    await expect(Page(props("ru"))).rejects.toMatchObject({
      digest: expect.stringContaining("NEXT_HTTP_ERROR_FALLBACK;404"),
    });
  });

  it("shows only title, genre and cover, and a clean CTA", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          title: "Бухта",
          genre: "pirates",
          cover_url: `/api/v1/share/${TOKEN}/cover.webp`,
          quests_done: 0,
          chapters: 0,
          family_id: "leak",
          names: ["Анна"],
        }),
        { status: 200 },
      ),
    );
    renderRu(await Page(props("ru")));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Бухта");
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      `/api/v1/share/${TOKEN}/cover.webp`,
    );
    // The public card keeps its one-line title height; only the sender's sheet reserves two lines.
    expect(
      screen.getByRole("heading", { level: 1 }).parentElement?.className ?? "",
    ).not.toContain("min-h");
    expect(document.body.textContent).not.toContain("leak");
    expect(document.body.textContent).not.toContain("Анна");
    expect(screen.getByRole("link", { name: "Создать свой мир" })).toHaveAttribute(
      "href",
      "/?source=share#demo",
    );
  });

  it("puts the genre words in the heading when there is no title; English CTA keeps the locale", async () => {
    fetchMock.mockResolvedValue(card(null, "fairy_tale"));
    renderRu(await Page(props("en")));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Сказка");
    expect(screen.getByRole("link")).toHaveAttribute("href", "/en?source=share#demo");
  });
});

describe("card layout", () => {
  it("starts with a skip link whose target is the card's main", async () => {
    fetchMock.mockResolvedValue(card("Бухта"));
    renderRu(<CardLayout>{await Page(props("ru"))}</CardLayout>);
    const skip = screen.getByRole("link", { name: "К содержимому" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(document.querySelector("a")).toBe(skip);
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });
});

describe("unavailable card", () => {
  it("says so and still invites to create a world", () => {
    renderRu(<ShareUnavailable locale="ru" />);
    expect(
      screen.getByRole("heading", { name: "Открытка недоступна" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Создать свой мир" })).toHaveAttribute(
      "href",
      "/?source=share#demo",
    );
  });
});

describe("share card counters", () => {
  it.each([
    [1, 1, "1 дело выполнено · 1 глава"],
    [3, 2, "3 дела выполнено · 2 главы"],
    [5, 21, "5 дел выполнено · 21 глава"],
    [12, 11, "12 дел выполнено · 11 глав"],
  ])("shows %i deeds and %i chapters in Russian plural forms", async (n, m, line) => {
    fetchMock.mockResolvedValue(card("Бухта", "pirates", n, m));
    renderRu(await Page(props("ru")));
    expect(document.querySelector("[data-share-counts]")).toHaveTextContent(line);
  });

  it.each([
    ["en", en, "1 quest done · 2 chapters"],
    ["es", es, "1 misión cumplida · 2 capítulos"],
    ["zh-CN", zh, "已完成 1 个任务 · 2 章"],
  ] as const)("speaks %s", (locale, messages, line) => {
    const t = createTranslator({ locale, messages, namespace: "share" });
    expect(t("counts", { quests: 1, chapters: 2 })).toBe(line);
  });

  it("hides the line while nothing is done yet", async () => {
    fetchMock.mockResolvedValue(card("Бухта"));
    renderRu(await Page(props("ru")));
    expect(document.querySelector("[data-share-counts]")).toBeNull();
  });

  it("rejects a negative counter", async () => {
    fetchMock.mockResolvedValue(card("Бухта", "pirates", -1, 0));
    await expect(Page(props("ru"))).rejects.toThrow();
  });
});
