import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Landing } from "@/components/landing";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import ru from "../messages/ru.json";
import en from "../messages/en.json";
import es from "../messages/es.json";
import zh from "../messages/zh-CN.json";
import { renderRu } from "./render";

const mocks = vi.hoisted(() => ({ pathname: "/", getMe: vi.fn() }));
vi.mock("@/i18n/navigation", async (original) => ({
  ...(await original<typeof import("@/i18n/navigation")>()),
  usePathname: () => mocks.pathname,
  useRouter: () => ({ replace: vi.fn() }),
}));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  getMe: mocks.getMe,
}));

describe("hero order on a phone", () => {
  it("puts the CTA buttons before a compact image, so the start button never falls below the fold", () => {
    const { container } = renderRu(<Landing />);
    const hero = container.querySelector("main > section") as HTMLElement;
    const h1 = hero.querySelector("h1") as HTMLElement;
    const img = hero.querySelector("img") as HTMLElement;
    const cta = screen.getByRole("link", { name: ru.landing.ctaTry });
    const before = Node.DOCUMENT_POSITION_FOLLOWING;
    expect(h1.compareDocumentPosition(cta) & before).toBeTruthy();
    expect(cta.compareDocumentPosition(img) & before).toBeTruthy();
    expect(img.className).toContain("aspect-[16/10]");
    expect(img.className).toContain("max-h-[40vh]");
    expect(img.className).toContain("sm:aspect-square");
  });

  it("keeps the lead and title free of entrance fades", () => {
    const { container } = renderRu(<Landing />);
    expect(container.querySelectorAll("main > section .rise")).toHaveLength(0);
  });
});

describe("landing header", () => {
  const nav = () => screen.queryByRole("navigation", { name: ru.nav.label });

  it("shows no app links and makes no request on the landing", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    mocks.getMe.mockClear();
    renderRu(<SiteHeader />);
    expect(nav()).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: ru.nav.home })).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(mocks.getMe).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("keeps app links on app pages", () => {
    mocks.pathname = "/play";
    renderRu(<SiteHeader />);
    expect(nav()).toBeInTheDocument();
    mocks.pathname = "/";
  });
});

describe("landing copy", () => {
  it("has no video placeholder", () => {
    renderRu(<Landing />);
    expect(screen.queryByRole("img", { name: /видео/i })).not.toBeInTheDocument();
    for (const m of [ru, en, es, zh]) expect("poster" in m.landing.gallery).toBe(false);
  });

  it("states the language scope as one muted footer line", () => {
    renderRu(<SiteFooter />);
    expect(
      screen.getByText("Игра на русском, английском, испанском и китайском"),
    ).toBeInTheDocument();
  });

  it("never lets a dash start a line in the ru and es hero strings (title, pitch only)", () => {
    for (const m of [ru, es]) {
      expect(m.landing.title).not.toMatch(/ — /);
      expect(m.landing.pitch).not.toMatch(/ — /);
    }
    expect(ru.landing.pitch).toContain("\u00a0— ");
    expect(ru.landing.pitch).toContain("о\u00a0вас. В\u00a0одиночку");
  });

  it("uses the agreed headline and lead", () => {
    expect(ru.landing.title).toBe(
      "Сказка, где герои\u00a0— вы, а\u00a0главы открывают настоящие дела",
    );
    expect(en.landing.title).toBe(
      "A story starring you, where real-life deeds unlock each chapter",
    );
  });
});
