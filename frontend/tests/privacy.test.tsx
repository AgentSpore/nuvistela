import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FamilyView } from "@/components/family-view";
import { Join } from "@/components/join";
import { NewFamily } from "@/components/new-family";
import { Policy } from "@/components/policy";
import { SiteFooter } from "@/components/site-footer";
import * as api from "@/lib/api";
import en from "../messages/en.json";
import es from "../messages/es.json";
import ru from "../messages/ru.json";
import zh from "../messages/zh-CN.json";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
  listMembers: vi.fn(),
  acceptInvite: vi.fn(),
}));
const replace = vi.hoisted(() => vi.fn());
vi.mock("@/i18n/navigation", async (orig) => ({
  ...(await orig<typeof import("@/i18n/navigation")>()),
  useRouter: () => ({ replace }),
}));
const m = vi.mocked(api);
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

beforeEach(() => {
  replace.mockClear();
  m.getMe.mockResolvedValue(member());
  m.listMembers.mockResolvedValue([member()]);
});
afterEach(() => fetchMock.mockReset());

const CONSENT = /Я родитель или законный представитель/;
const created = {
  family_id: "f1",
  member: member(),
  invite_url: "/api/v1/invite/t1",
};

describe("/new consent", () => {
  async function fillForm() {
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Название игры"), "Ивановы");
    await user.type(screen.getByLabelText("Ваше имя"), "Анна");
    return user;
  }

  it("keeps submit disabled until the checkbox is ticked", async () => {
    renderRu(<NewFamily />);
    const user = await fillForm();
    const submit = screen.getByRole("button", { name: "Продолжить" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: CONSENT }));
    expect(submit).toBeEnabled();
    await user.click(screen.getByRole("checkbox", { name: CONSENT }));
    expect(submit).toBeDisabled();
  });

  it("links the policy and posts privacy_consent: true", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify(created), { status: 200 }));
    renderRu(<NewFamily />);
    const link = screen.getByRole("link", { name: "политику конфиденциальности" });
    expect(link.getAttribute("href")).toMatch(/\/privacy$/);
    const user = await fillForm();
    await user.click(screen.getByRole("checkbox", { name: CONSENT }));
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await screen.findByRole("link", { name: "Перейти к игре" });
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body).toMatchObject({ title: "Ивановы", privacy_consent: true });
  });
});

describe("/join and footer", () => {
  it("states acceptance with a policy link on /join", async () => {
    m.acceptInvite.mockRejectedValue(new api.ApiError("http", 401));
    renderRu(<Join />);
    const link = await screen.findByRole("link", { name: "политику конфиденциальности" });
    expect(link.getAttribute("href")).toMatch(/\/privacy$/);
    expect(link.parentElement).toHaveTextContent("Продолжая, вы принимаете");
  });

  it("links the policy from the footer in every locale", () => {
    for (const [locale, msgs, name] of [
      ["ru", ru, "Политика конфиденциальности"],
      ["en", en, "Privacy policy"],
      ["es", es, "Política de privacidad"],
      ["zh-CN", zh, "隐私政策"],
    ] as const) {
      const { unmount } = render(
        <NextIntlClientProvider locale={locale} messages={msgs}>
          <SiteFooter />
        </NextIntlClientProvider>,
      );
      const a = screen.getByRole("link", { name });
      expect(a.getAttribute("href")).toMatch(/\/privacy$/);
      unmount();
    }
  });
});

describe("policy text", () => {
  it("renders headings, paragraphs, bullet lists, bold and code", () => {
    const { container } = render(
      <Policy
        sections={[{ h: "Раздел", p: ["Абзац", "- один `code`", "- **два**", "Хвост"] }]}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Раздел" })).toBeInTheDocument();
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    expect(container.querySelector("code")).toHaveTextContent("code");
    expect(container.querySelector("strong")).toHaveTextContent("два");
    expect(container.querySelectorAll("p")).toHaveLength(2);
  });

  it("ships the same shape, version, operator and email placeholder in all four locales", () => {
    for (const msg of [ru, en, es, zh]) {
      expect(msg.privacy.version).toBe("2026-11-18");
      expect(JSON.stringify(msg.privacy)).toMatch(/[OGRNIP]/);
      expect(JSON.stringify(msg.privacy)).not.toMatch(
        /\[(operator|оператор|operador|运营方)\]/,
      );
      expect(msg.privacy.sections).toHaveLength(ru.privacy.sections.length);
      msg.privacy.sections.forEach((s, i) =>
        expect(s.p).toHaveLength(ru.privacy.sections[i]!.p.length),
      );
      expect(JSON.stringify(msg.privacy)).not.toMatch(/\[(email|почта|correo|邮箱)\]/);
      expect(JSON.stringify(msg.privacy).match(/privacy@example\.com/g)).toHaveLength(3);
    }
  });
});

describe("/family delete", () => {
  const owner = () =>
    m.getMe.mockResolvedValue(member({ is_owner: true }));
  const open = async () => {
    renderRu(<FamilyView />);
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Удалить семью и все данные" }),
    );
    return user;
  };

  it("offers deletion to the owner only", async () => {
    renderRu(<FamilyView />);
    await screen.findByRole("heading", { name: "Добавить участника" });
    expect(
      screen.queryByRole("button", { name: "Удалить семью и все данные" }),
    ).toBeNull();
  });

  it("gates the final button on the typed confirmation word, then deletes and goes home", async () => {
    owner();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const user = await open();
    const confirm = screen.getByRole("button", { name: "Удалить навсегда" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Подтверждение"), "УДАЛИТ");
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Подтверждение"), "Ь");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toMatch(/\/families\/f1$/);
    expect(init?.method).toBe("DELETE");
  });

  it("shows an error and stays put on 403", async () => {
    owner();
    fetchMock.mockResolvedValue(new Response("{}", { status: 403 }));
    const user = await open();
    await user.type(screen.getByLabelText("Подтверждение"), "УДАЛИТЬ");
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Удалить навсегда" }));
    });
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/только взрослым/)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
