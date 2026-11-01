import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "@/components/composer";
import { Play } from "@/components/play";
import { TelegramCard } from "@/components/telegram-card";
import * as api from "@/lib/api";
import ru from "../messages/ru.json";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
  listMembers: vi.fn(),
  sendAgentMessage: vi.fn(),
  issueTelegramCode: vi.fn(),
}));
const m = vi.mocked(api);
const code = (over: Partial<api.LinkCode> = {}): api.LinkCode => ({
  code: "AB12CD",
  expires_at: new Date(Date.now() + 600_000).toISOString(),
  bot_username: "BumbliBot",
  ...over,
});
const getCode = async () =>
  userEvent.click(screen.getByRole("button", { name: "Получить код" }));

beforeEach(() => {
  vi.clearAllMocks();
  m.getMe.mockResolvedValue(member());
  m.listMembers.mockResolvedValue([member()]);
});
afterEach(() => vi.unstubAllGlobals());

describe("telegram card", () => {
  it("formats the expiry in the browser time zone, not the provider's", async () => {
    const was = process.env.TZ;
    process.env.TZ = "Asia/Tokyo";
    m.issueTelegramCode.mockResolvedValue(code({ expires_at: "2026-11-01T04:15:00Z" }));
    render(
      <NextIntlClientProvider locale="ru" messages={ru} timeZone="UTC">
        <TelegramCard familyId="f1" />
      </NextIntlClientProvider>,
    );
    await getCode();
    expect(await screen.findByText(/до 13:15/)).toBeInTheDocument();
    process.env.TZ = was;
  });

  it("does not promise a fixed duration", async () => {
    m.issueTelegramCode.mockResolvedValue(code());
    renderRu(<TelegramCard familyId="f1" />);
    await getCode();
    expect(await screen.findByText(/Код действует до/)).toBeInTheDocument();
    expect(screen.queryByText(/минут/)).not.toBeInTheDocument();
  });

  it("shows the command with the bot username and an add-to-group link", async () => {
    m.issueTelegramCode.mockResolvedValue(code());
    renderRu(<TelegramCard familyId="f1" />);
    await getCode();
    expect(await screen.findByText("/link@BumbliBot AB12CD")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Добавить бота в группу" })).toHaveAttribute(
      "href",
      "https://t.me/BumbliBot?startgroup=1",
    );
  });

  it("offers no command while the bot is not connected", async () => {
    m.issueTelegramCode.mockResolvedValue(code({ bot_username: null }));
    renderRu(<TelegramCard familyId="f1" />);
    await getCode();
    expect(await screen.findByText(/Telegram ещё не подключён/)).toBeInTheDocument();
    expect(screen.queryByText(/\/link/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Добавить бота в группу" })).toBeNull();
  });

  it("says so when the clipboard is denied", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    m.issueTelegramCode.mockResolvedValue(code());
    renderRu(<TelegramCard familyId="f1" />);
    await getCode();
    await userEvent.click(
      await screen.findByRole("button", { name: "Копировать команду" }),
    );
    expect(await screen.findByText(/Не удалось скопировать/)).toBeInTheDocument();
  });
});

describe("api contract", () => {
  it("requires is_owner", () => {
    const legacy: Record<string, unknown> = { ...member() };
    delete legacy.is_owner;
    expect(api.memberResponseSchema.safeParse(legacy).success).toBe(false);
  });
});

describe("composer", () => {
  it("ignores the Enter that commits an IME composition (keyCode 229)", () => {
    const onSend = vi.fn();
    renderRu(<Composer value="こん" onChange={() => {}} onSend={onSend} busy={false} />);
    const box = screen.getByLabelText("Сообщение ведущему");
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter", keyCode: 13 });
    expect(onSend).toHaveBeenCalledOnce();
  });
});

describe("/play", () => {
  async function sendHeld(text: string) {
    let fail: (e: unknown) => void = () => {};
    m.sendAgentMessage.mockReturnValue(new Promise((_, rej) => (fail = rej)));
    renderRu(<Play />);
    const box = await screen.findByLabelText("Сообщение ведущему");
    await userEvent.type(box, text);
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
    return { box, fail };
  }

  it("keeps the failed text when the user typed during the wait", async () => {
    const { box, fail } = await sendHeld("Привет");
    await userEvent.type(box, "Б");
    fail(new api.ApiError("http", 429));
    await waitFor(() => expect(box).toHaveValue("Привет\nБ"));
  });

  it("shows a retry when the roster fails to load", async () => {
    m.listMembers.mockRejectedValueOnce(new api.ApiError("network", 0));
    renderRu(<Play />);
    const retry = await screen.findByRole("button", { name: "Повторить" });
    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось загрузить");
    await userEvent.click(retry);
    expect(await screen.findByRole("list", { name: "Семья" })).toBeInTheDocument();
  });

  describe("autoscroll", () => {
    function geometry(el: HTMLElement) {
      let top = 0;
      Object.defineProperty(el, "scrollHeight", { value: 1000, configurable: true });
      Object.defineProperty(el, "clientHeight", { value: 400, configurable: true });
      Object.defineProperty(el, "scrollTop", {
        get: () => top,
        set: (v: number) => (top = v),
        configurable: true,
      });
    }
    async function setup() {
      let reply: (v: { reply: string }) => void = () => {};
      m.sendAgentMessage.mockReturnValue(new Promise((r) => (reply = r)));
      renderRu(<Play />);
      const box = await screen.findByLabelText("Сообщение ведущему");
      const scroller = screen.getByRole("log").parentElement as HTMLElement;
      geometry(scroller);
      await userEvent.type(box, "Привет");
      await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
      return { scroller, reply };
    }

    it("follows the bottom on own send and when the reader is at the bottom", async () => {
      const { scroller, reply } = await setup();
      expect(scroller.scrollTop).toBe(1000);
      scroller.scrollTop = 600;
      fireEvent.scroll(scroller);
      reply({ reply: "Ответ" });
      await screen.findByText("Ответ");
      expect(scroller.scrollTop).toBe(1000);
    });

    it("leaves a reader who scrolled up alone", async () => {
      const { scroller, reply } = await setup();
      scroller.scrollTop = 100;
      fireEvent.scroll(scroller);
      reply({ reply: "Ответ" });
      await screen.findByText("Ответ");
      expect(scroller.scrollTop).toBe(100);
    });
  });
});
