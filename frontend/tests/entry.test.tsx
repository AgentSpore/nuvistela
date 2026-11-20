import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import { FamilyView } from "@/components/family-view";
import { InviteLink } from "@/components/invite-link";
import { Join } from "@/components/join";
import { NewFamily } from "@/components/new-family";
import { Play } from "@/components/play";
import * as adv from "@/lib/adventure-api";
import * as api from "@/lib/api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
  listMembers: vi.fn(),
  sendAgentMessage: vi.fn(),
  createFamily: vi.fn(),
  acceptInvite: vi.fn(),
  addMember: vi.fn(),
  reissueInvite: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
}));
const replace = vi.hoisted(() => vi.fn());
vi.mock("@/i18n/navigation", async (orig) => ({
  ...(await orig<typeof import("@/i18n/navigation")>()),
  useRouter: () => ({ replace }),
}));
const m = vi.mocked(api);
const a = vi.mocked(adv);

const owner = member({ id: "o1", display_name: "Анна", is_owner: true });
const child = member({ id: "k1", display_name: "Маша", age_band: "6-9", role: "child" });

beforeEach(() => {
  vi.clearAllMocks();
  m.getMe.mockResolvedValue(child);
  m.listMembers.mockResolvedValue([owner, child]);
});
afterEach(() => vi.useRealTimers());

describe("entry goes to the adventure", () => {
  it("an accepted invite lands on /adventure, not the chat", async () => {
    window.location.hash = "#t1";
    m.acceptInvite.mockResolvedValue(undefined as never);
    renderRu(<Join />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/adventure"));
  });
});

describe("a player before the world exists", () => {
  it("sees who is choosing the world, then the quest without a reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const quest = {
      id: "q1",
      seq: 1,
      title: "Построить шалаш",
      description: "Соберите шалаш из подушек.",
      skill: "teamwork",
      source: "template" as const,
      status: "open" as const,
    };
    a.getAdventure
      .mockResolvedValueOnce({ world: null, quest: null, chapters: [] })
      .mockResolvedValue({ world: null, quest, chapters: [] });
    renderRu(<Adventure />);
    expect(
      await screen.findByText("Анна выбирает ваш мир — скоро начнём!"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Попросите взрослого/)).toBeNull();
    await act(() => vi.advanceTimersByTimeAsync(3500));
    expect(await screen.findByText("Построить шалаш")).toBeInTheDocument();
  });
});

describe("world wait headline", () => {
  it("appears once, with the name, only after the roster has loaded", async () => {
    let resolve: (l: api.Member[]) => void = () => {};
    m.listMembers.mockReturnValue(new Promise((r) => (resolve = r)));
    a.getAdventure.mockResolvedValue({ world: null, quest: null, chapters: [] });
    renderRu(<Adventure />);
    const hint = await screen.findByText(/Первое задание появится/);
    const status = hint.closest("[role=status]");
    expect(status).not.toHaveTextContent(/выбирает ваш мир/);
    await act(async () => resolve([owner, child]));
    expect(status).toHaveTextContent("Анна выбирает ваш мир — скоро начнём!");
  });
});

describe("empty chat starters", () => {
  it("a starter sends its text in one tap", async () => {
    m.sendAgentMessage.mockResolvedValue({ reply: "Привет!" } as never);
    renderRu(<Play />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Придумай загадку" }),
    );
    expect(m.sendAgentMessage).toHaveBeenCalledWith("Придумай загадку");
    expect(
      await within(screen.getByRole("log")).findByText("Привет!"),
    ).toBeInTheDocument();
  });

  it("a starter leaves a typed draft alone", async () => {
    m.sendAgentMessage.mockResolvedValue({ reply: "Привет!" } as never);
    renderRu(<Play />);
    await userEvent.type(await screen.findByLabelText("Сообщение ведущему"), "моё");
    await userEvent.click(screen.getByRole("button", { name: "Придумай загадку" }));
    await screen.findByText("Привет!");
    expect(screen.getByLabelText("Сообщение ведущему")).toHaveValue("моё");
  });

  it("a failed starter does not land in the draft", async () => {
    m.sendAgentMessage.mockRejectedValue(new api.ApiError("http", 503));
    renderRu(<Play />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Придумай загадку" }),
    );
    await screen.findByText("Ведущий недоступен");
    expect(screen.getByLabelText("Сообщение ведущему")).toHaveValue("");
    expect(screen.queryByText(/Текст вернулся/)).toBeNull();
  });
});

describe("invite link share", () => {
  afterEach(() => {
    Reflect.deleteProperty(navigator, "share");
  });

  it("hands the link to the system share sheet", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "share", { value: share, configurable: true });
    renderRu(<InviteLink name="Маша" url="http://x/join#t" />);
    await userEvent.click(screen.getByRole("button", { name: "Поделиться" }));
    expect(share).toHaveBeenCalledWith({ url: "http://x/join#t" });
  });

  it("a dismissed share sheet neither copies nor reports", async () => {
    const abort = new DOMException("dismissed", "AbortError");
    Object.defineProperty(navigator, "share", {
      value: vi.fn().mockRejectedValue(abort),
      configurable: true,
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderRu(<InviteLink name="Маша" url="http://x/join#t" />);
    await userEvent.click(screen.getByRole("button", { name: "Поделиться" }));
    expect(writeText).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("a refused share falls back to copying", async () => {
    const denied = new DOMException("denied", "NotAllowedError");
    Object.defineProperty(navigator, "share", {
      value: vi.fn().mockRejectedValue(denied),
      configurable: true,
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderRu(<InviteLink name="Маша" url="http://x/join#t" />);
    await userEvent.click(screen.getByRole("button", { name: "Поделиться" }));
    expect(writeText).toHaveBeenCalledWith("http://x/join#t");
  });

  it("copies the link where sharing is unavailable", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    renderRu(<InviteLink name="Маша" url="http://x/join#t" />);
    await userEvent.click(screen.getByRole("button", { name: "Поделиться" }));
    expect(writeText).toHaveBeenCalledWith("http://x/join#t");
  });
});

describe("/new for one player", () => {
  it("leads straight to choosing a world, links appear once someone is added", async () => {
    m.createFamily.mockResolvedValue({
      family_id: "f1",
      member: owner,
      invite_url: "/api/v1/invite/t1",
    });
    m.addMember.mockResolvedValue({ member: child, invite_url: "/api/v1/invite/t2" });
    renderRu(<NewFamily />);
    await userEvent.type(screen.getByLabelText("Название игры"), "Я");
    await userEvent.type(screen.getByLabelText("Ваше имя"), "Анна");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    const go = await screen.findByRole("link", { name: "Перейти к игре" });
    expect(go).toHaveAttribute("href", "/adventure");
    expect(screen.queryByRole("heading", { name: "Ссылки для входа" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Добавить участника" }));
    await userEvent.type(screen.getByLabelText("Имя"), "Маша");
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }));
    expect(await screen.findByLabelText("Ссылка для входа: Маша")).toBeInTheDocument();
    expect(screen.getByText(/Ссылка видна один раз/)).toBeInTheDocument();
  });
});

describe("/family invite links", () => {
  const once = /Ссылка видна один раз/;

  it("says a new link is shown once after adding a player", async () => {
    m.getMe.mockResolvedValue(owner);
    m.addMember.mockResolvedValue({ member: child, invite_url: "/api/v1/invite/t2" });
    renderRu(<FamilyView />);
    await userEvent.type(await screen.findByLabelText("Имя"), "Маша");
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }));
    await screen.findByLabelText("Ссылка для входа: Маша");
    expect(screen.getByText(once)).toBeInTheDocument();
  });

  it("says a reissued link is shown once", async () => {
    m.getMe.mockResolvedValue(owner);
    m.reissueInvite.mockResolvedValue({ invite_url: "/api/v1/invite/t3" } as never);
    renderRu(<FamilyView />);
    await userEvent.click(await screen.findByRole("button", { name: /Маша/ }));
    await screen.findByLabelText("Ссылка для входа: Маша");
    expect(screen.getByText("Ссылка видна один раз.")).toBeInTheDocument();
    expect(screen.queryByText(/нажмите «Новая ссылка»/)).toBeNull();
  });
});
