import { renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FamilyView } from "@/components/family-view";
import { Play } from "@/components/play";
import { TelegramCard } from "@/components/telegram-card";
import * as api from "@/lib/api";
import { agentNoteKey, errorKey } from "@/lib/errors";
import { canReissue } from "@/lib/reissue";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
  listMembers: vi.fn(),
  sendAgentMessage: vi.fn(),
  issueTelegramCode: vi.fn(),
}));
const m = vi.mocked(api);
const http = (status: number) => new api.ApiError("http", status);

const owner = member({ id: "o", display_name: "Олег", is_owner: true });
const mom = member({ id: "a", display_name: "Анна" });
const dad = member({ id: "d", display_name: "Дима" });
const kid = member({ id: "k", display_name: "Маша", age_band: "6-9", role: "child" });
const roster = [owner, mom, dad, kid];

function setSession(me: api.Member) {
  m.getMe.mockResolvedValue(me);
  m.listMembers.mockResolvedValue(roster);
}
const reissueLabels = () =>
  screen
    .queryAllByRole("button", { name: /Новая ссылка/ })
    .map((b) => b.getAttribute("aria-label"));

beforeEach(() => vi.clearAllMocks());

describe("status mapping for the game master", () => {
  it.each([
    [409, "busy"],
    [429, "limit"],
    [503, "unavailable"],
    [422, "textTooLong"],
    [404, "soon"],
    [501, "soon"],
    [500, "failed"],
  ])("maps HTTP %i to %s", (status, key) => {
    expect(agentNoteKey(http(status))).toBe(key);
  });

  it("maps transport and auth failures", () => {
    expect(agentNoteKey(new api.ApiError("network", 0))).toBe("network");
    expect(agentNoteKey(http(401))).toBe("unauthorized");
    expect(errorKey(http(409))).toBe("generic");
  });

  it.each([
    [409, "Ведущий ещё отвечает"],
    [429, "Дневной лимит вашей семьи исчерпан"],
    [503, "Ведущий сейчас недоступен"],
  ])(
    "shows a human message for %i and returns the text to the box",
    async (status, text) => {
      setSession(mom);
      m.sendAgentMessage.mockRejectedValue(http(status));
      renderRu(<Play />);
      const box = await screen.findByLabelText("Сообщение ведущему");
      await userEvent.type(box, "Привет");
      await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
      expect(await screen.findByText(new RegExp(text))).toBeInTheDocument();
      expect(box).toHaveValue("Привет");
    },
  );
});

describe("composer", () => {
  it("sends on Enter, keeps a newline on Shift+Enter and disables send while busy", async () => {
    setSession(mom);
    let done!: (v: { reply: string }) => void;
    m.sendAgentMessage.mockReturnValue(new Promise((r) => (done = r)));
    renderRu(<Play />);
    const box = await screen.findByLabelText("Сообщение ведущему");
    await userEvent.type(box, "строка{Shift>}{Enter}{/Shift}вторая");
    expect(box).toHaveValue("строка\nвторая");
    await userEvent.type(box, "{Enter}");
    expect(m.sendAgentMessage).toHaveBeenCalledWith("строка\nвторая");
    expect(screen.getByRole("button", { name: "Отправить" })).toBeDisabled();
    expect(screen.getByText("Ведущий пишет…")).toBeInTheDocument();
    done({ reply: "Глава первая" });
    expect(await screen.findByText("Глава первая")).toBeInTheDocument();
  });

  it("shows the counter near 2000 characters and blocks sending past it", async () => {
    setSession(mom);
    renderRu(<Play />);
    const box = await screen.findByLabelText("Сообщение ведущему");
    expect(screen.queryByText(/из 2000/)).toBeNull();
    await userEvent.click(box);
    await userEvent.paste("а".repeat(1700));
    expect(screen.getByText("1700 из 2000")).toBeInTheDocument();
    await userEvent.paste("а".repeat(400));
    expect(screen.getByText("2100 из 2000")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить" })).toBeDisabled();
  });
});

describe("who may reissue whose link", () => {
  it.each([
    ["owner", owner, [owner, mom, dad, kid].map((x) => x.id)],
    ["adult", mom, [mom.id, kid.id]],
    ["child", kid, []],
  ])("%s", (_n, me, allowedIds) => {
    expect(roster.filter((x) => canReissue(me, x)).map((x) => x.id)).toEqual(allowedIds);
  });

  it("renders the matrix: owner sees every member, adult only child and self, child nothing", async () => {
    setSession(owner);
    const view = renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    expect(reissueLabels()).toHaveLength(4);
    view.unmount();

    setSession(mom);
    const second = renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    expect(reissueLabels()).toEqual(["Новая ссылка: Анна", "Новая ссылка: Маша"]);
    second.unmount();

    setSession(kid);
    renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    expect(reissueLabels()).toEqual([]);
    expect(screen.queryByRole("heading", { name: "Подключить Telegram" })).toBeNull();
  });

  it("marks the owner in the roster", async () => {
    setSession(mom);
    renderRu(<FamilyView />);
    await screen.findByText("Олег", { selector: "p" });
    expect(screen.getAllByText("Владелец")).toHaveLength(1);
  });
});

describe("telegram card", () => {
  it("is offered to adults", async () => {
    setSession(mom);
    renderRu(<FamilyView />);
    expect(
      await screen.findByRole("heading", { name: "Подключить Telegram" }),
    ).toBeInTheDocument();
  });

  it("shows the command with the code and the 10 minute expiry", async () => {
    const expires = new Date(Date.now() + 600_000).toISOString();
    m.issueTelegramCode.mockResolvedValue({ code: "AB12CD", expires_at: expires });
    renderRu(<TelegramCard familyId="f1" />);
    await userEvent.click(screen.getByRole("button", { name: "Получить код" }));
    expect(await screen.findByText("/link@bot AB12CD")).toBeInTheDocument();
    expect(screen.getByText(/Код действует 10 минут/)).toBeInTheDocument();
    expect(m.issueTelegramCode).toHaveBeenCalledWith("f1");
  });

  it("explains a 403 without showing a code", async () => {
    m.issueTelegramCode.mockRejectedValue(http(403));
    renderRu(<TelegramCard familyId="f1" />);
    await userEvent.click(screen.getByRole("button", { name: "Получить код" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("только взрослым");
  });
});

describe("legacy member payload", () => {
  it("defaults is_owner to false", async () => {
    const { result } = renderHook(() =>
      api.memberResponseSchema.parse({ ...mom, is_owner: undefined }),
    );
    await waitFor(() => expect(result.current.is_owner).toBe(false));
  });
});
