import { act, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Join } from "@/components/join";
import { FamilyView } from "@/components/family-view";
import { InviteLink } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { NewFamily } from "@/components/new-family";
import { Play } from "@/components/play";
import * as api from "@/lib/api";
import { useMembers } from "@/lib/use-me";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
  listMembers: vi.fn(),
  sendAgentMessage: vi.fn(),
  createFamily: vi.fn(),
  reissueInvite: vi.fn(),
  acceptInvite: vi.fn(),
  addMember: vi.fn(),
}));
const replace = vi.hoisted(() => vi.fn());
vi.mock("@/i18n/navigation", async (orig) => ({
  ...(await orig<typeof import("@/i18n/navigation")>()),
  useRouter: () => ({ replace }),
}));
const m = vi.mocked(api);

beforeEach(() => {
  m.getMe.mockResolvedValue(member());
  m.listMembers.mockResolvedValue([
    member(),
    member({ id: "m2", display_name: "Маша", age_band: "6-9", role: "child" }),
  ]);
});

describe("/play", () => {
  it("shows the agent reply with its own bubble", async () => {
    m.sendAgentMessage.mockResolvedValue({ reply: "Привет, герой!" });
    renderRu(<Play />);
    await userEvent.type(await screen.findByLabelText("Сообщение ведущему"), "Привет");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findByText("Привет, герой!")).toBeInTheDocument();
    expect(screen.getByText("Привет")).toBeInTheDocument();
  });

  it("lists members from the API", async () => {
    renderRu(<Play />);
    expect(await screen.findByText("Маша")).toBeInTheDocument();
  });
});

describe("/family", () => {
  it("offers a non-owner adult reissue for a child and for self", async () => {
    renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    const names = screen
      .getAllByRole("button", { name: /Новая ссылка/ })
      .map((b) => b.getAttribute("aria-label"));
    expect(names).toEqual(["Новая ссылка: Анна", "Новая ссылка: Маша"]);
  });

  it("hosts the add-member form for adults", async () => {
    renderRu(<FamilyView />);
    expect(
      await screen.findByRole("heading", { name: "Добавить участника" }),
    ).toBeInTheDocument();
  });

  it("hides the add-member form from children", async () => {
    m.getMe.mockResolvedValue(member({ role: "child", age_band: "6-9" }));
    renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    expect(screen.queryByRole("heading", { name: "Добавить участника" })).toBeNull();
  });
});

const CONSENT = /Я родитель или законный представитель/;
const consent = () => userEvent.click(screen.getByRole("checkbox", { name: CONSENT }));

describe("/new", () => {
  it("focuses the first invalid field after a failed submit", async () => {
    renderRu(<NewFamily />);
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    await waitFor(() => expect(screen.getByLabelText("Название игры")).toHaveFocus());
  });

  it.each([
    ["rate_limited", "Слишком много попыток, попробуйте через час"],
    ["daily_full", "Сегодня все места заняты — приходите завтра"],
  ])("tells a warm story for the refusal %s", async (code, text) => {
    m.createFamily.mockRejectedValue(new api.ApiError("http", 429, code));
    renderRu(<NewFamily />);
    await userEvent.type(screen.getByLabelText("Название игры"), "Ивановы");
    await userEvent.type(screen.getByLabelText("Ваше имя"), "Анна");
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(await screen.findByText(text)).toBeVisible();
  });

  it("hides a lone creator's link and the add form after creation", async () => {
    m.createFamily.mockResolvedValue({
      family_id: "f1",
      member: member(),
      invite_url: "/api/v1/invite/t1",
    });
    renderRu(<NewFamily />);
    await userEvent.type(screen.getByLabelText("Название игры"), "Ивановы");
    await userEvent.type(screen.getByLabelText("Ваше имя"), "Анна");
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(await screen.findByRole("link", { name: "Перейти к игре" })).toBeVisible();
    expect(screen.queryByLabelText("Ссылка для входа: Анна")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Добавить участника" })).toBeNull();
  });

  it("makes the way into the game primary and reveals the member form on demand", async () => {
    m.createFamily.mockResolvedValue({
      family_id: "f1",
      member: member(),
      invite_url: "/api/v1/invite/t1",
    });
    renderRu(<NewFamily />);
    await userEvent.type(screen.getByLabelText("Название игры"), "Ивановы");
    await userEvent.type(screen.getByLabelText("Ваше имя"), "Анна");
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    const play = await screen.findByRole("link", { name: "Перейти к игре" });
    expect(play).toHaveClass("btn-primary");
    const add = screen.getByRole("button", { name: "Добавить участника" });
    expect(add).not.toHaveClass("btn-primary");
    await userEvent.click(add);
    expect(
      screen.getByRole("heading", { name: "Добавить участника" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Имя")).toHaveFocus();
    expect(screen.queryByLabelText("Роль")).toBeNull();
  });
});

describe("/new after creation", () => {
  const create = async () => {
    m.createFamily.mockResolvedValue({
      family_id: "f1",
      member: member(),
      invite_url: "/api/v1/invite/t1",
    });
    renderRu(<NewFamily />);
    await userEvent.type(screen.getByLabelText("Название игры"), "Ивановы");
    await userEvent.type(screen.getByLabelText("Ваше имя"), "Анна");
    await consent();
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    await screen.findByRole("link", { name: "Перейти к игре" });
  };
  const current = () =>
    within(screen.getByRole("list", { name: "Шаги" }))
      .getAllByRole("listitem")
      .find((li) => li.getAttribute("aria-current") === "step");

  it("does not call the second step links when a lone player has none", async () => {
    await create();
    expect(current()).toHaveTextContent("Готово");
    expect(screen.queryByText("Ссылки")).toBeNull();
  });

  it("collapses the member form after an addition and reopens it on demand", async () => {
    await create();
    m.addMember.mockResolvedValue({
      member: member({ id: "m2", display_name: "Петя" }),
      invite_url: "/api/v1/invite/t2",
    });
    await userEvent.click(screen.getByRole("button", { name: "Добавить участника" }));
    await userEvent.type(screen.getByLabelText("Имя"), "Петя");
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }));
    const again = await screen.findByRole("button", { name: "Добавить ещё участника" });
    expect(screen.queryByRole("heading", { name: "Добавить участника" })).toBeNull();
    expect(again).toHaveFocus();
    expect(
      screen.getByText("Ссылка готова: Петя").closest('[role="status"]'),
    ).not.toBeNull();
    expect(current()).toHaveTextContent("Ссылки");
    await userEvent.click(again);
    expect(screen.getByLabelText("Имя")).toHaveValue("");
  });

  it("announces each addition, even of a second player with the same name", async () => {
    await create();
    const addPetya = async (id: string) => {
      m.addMember.mockResolvedValueOnce({
        member: member({ id, display_name: "Петя" }),
        invite_url: `/api/v1/invite/${id}`,
      });
      await userEvent.click(
        screen.getByRole("button", { name: /^Добавить (ещё )?участника$/ }),
      );
      await userEvent.type(screen.getByLabelText("Имя"), "Петя");
      await userEvent.click(screen.getByRole("button", { name: "Добавить" }));
      return screen.findByText("Ссылка готова: Петя");
    };
    const first = await addPetya("m2");
    const second = await addPetya("m3");
    expect(second).not.toBe(first);
    expect(second.closest('[role="status"]')).not.toBeNull();
  });
});

describe("member form derives the role from age", () => {
  it.each([
    ["adult", "adult"],
    ["6-9", "child"],
  ] as const)("age %s is sent with role %s", async (band, role) => {
    m.addMember.mockResolvedValue({ member: member(), invite_url: "/api/v1/invite/t2" });
    renderRu(<MemberForm familyId="f1" onAdded={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Имя"), "Маша");
    await userEvent.selectOptions(screen.getByLabelText("Возраст"), band);
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }));
    expect(m.addMember).toHaveBeenCalledWith(
      "f1",
      expect.objectContaining({ age_band: band, role }),
    );
  });
});

describe("invite link", () => {
  it("says so when the clipboard is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      configurable: true,
    });
    renderRu(<InviteLink name="Анна" url="http://x/y" />);
    await userEvent.click(screen.getByRole("button", { name: "Копировать" }));
    expect(
      await screen.findByText("Не удалось скопировать, выделите ссылку вручную"),
    ).toBeInTheDocument();
  });
});

describe("reissue rules", () => {
  it("maps 403 to the forbidden message", async () => {
    m.reissueInvite.mockRejectedValue(new api.ApiError("http", 403));
    renderRu(<FamilyView />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Новая ссылка: Маша" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Это действие доступно только взрослым.",
    );
  });
});

describe("useMembers", () => {
  it("exposes a load failure", async () => {
    m.listMembers.mockRejectedValue(new api.ApiError("network", 0));
    const { result } = renderHook(() => useMembers("f1"));
    await waitFor(() => expect(result.current.failed).toBe(true));
  });

  it("drops a stale response that resolves last", async () => {
    let late!: (v: api.Member[]) => void;
    m.listMembers
      .mockReturnValueOnce(new Promise((r) => (late = r)))
      .mockResolvedValueOnce([member({ id: "new" })]);
    const { result, rerender } = renderHook(({ id }) => useMembers(id), {
      initialProps: { id: "f1" },
    });
    rerender({ id: "f2" });
    await waitFor(() => expect(result.current.members[0]?.id).toBe("new"));
    late([member({ id: "stale" })]);
    await new Promise((r) => setTimeout(r, 10));
    expect(result.current.members[0]?.id).toBe("new");
  });

  it("ignores a stale failure that arrives after a fresh success", async () => {
    let lateFail!: (e: unknown) => void;
    m.listMembers
      .mockReturnValueOnce(new Promise((_, rej) => (lateFail = rej)))
      .mockResolvedValueOnce([member({ id: "new" })]);
    const { result, rerender } = renderHook(({ id }) => useMembers(id), {
      initialProps: { id: "f1" },
    });
    rerender({ id: "f2" });
    await waitFor(() => expect(result.current.members[0]?.id).toBe("new"));
    lateFail(new api.ApiError("network", 0));
    await new Promise((r) => setTimeout(r, 10));
    expect(result.current.failed).toBe(false);
  });

  it("renders an alert on /family when the roster fails", async () => {
    m.listMembers.mockRejectedValue(new api.ApiError("http", 500));
    renderRu(<FamilyView />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("errors reach assistive tech before focus", () => {
  it("field is already described by its error when it receives focus", async () => {
    renderRu(<NewFamily />);
    await consent();
    const field = screen.getByLabelText("Название игры");
    let seen: string | null = "unset";
    field.addEventListener(
      "focus",
      () => (seen = field.getAttribute("aria-describedby")),
    );
    await userEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(seen).toBe("f-title-err");
    expect(field).toHaveAccessibleDescription("Заполните это поле");
  });
});

describe("/play without secure-context crypto", () => {
  it("still sends and shows messages", async () => {
    vi.stubGlobal("crypto", {});
    m.sendAgentMessage.mockResolvedValue({ reply: "ок" });
    renderRu(<Play />);
    await userEvent.type(await screen.findByLabelText("Сообщение ведущему"), "эй");
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));
    expect(await screen.findByText("ок")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe("/join", () => {
  const open = (hash: string) => window.history.replaceState(null, "", `/join${hash}`);
  const renderJoin = () =>
    renderRu(
      <StrictMode>
        <Join />
      </StrictMode>,
    );
  beforeEach(() => replace.mockClear());

  it("consumes the token once, clears the address bar and enters the game", async () => {
    open("#tok123");
    let hashAtCall: string | null = null;
    m.acceptInvite.mockImplementation(async () => {
      hashAtCall = window.location.hash;
      return member();
    });
    renderJoin();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/adventure"));
    expect(hashAtCall).toBe("");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(m.acceptInvite).toHaveBeenCalledTimes(1);
    expect(m.acceptInvite).toHaveBeenCalledWith("tok123");
    expect(window.location.hash).toBe("");
  });

  it("explains an invalid or used link on 401", async () => {
    open("#bad");
    m.acceptInvite.mockRejectedValue(new api.ApiError("http", 401));
    renderJoin();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Попросите взрослого выпустить новую",
    );
    expect(replace).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("");
  });

  it.each([422])("treats %i as an invalid link too", async (status) => {
    open("#huge");
    m.acceptInvite.mockRejectedValue(new api.ApiError("http", status));
    renderJoin();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Попросите взрослого выпустить новую",
    );
  });

  it("says to wait when the address is rate limited, not a generic failure", async () => {
    open("#tok");
    m.acceptInvite.mockRejectedValue(new api.ApiError("http", 429, "rate_limited"));
    renderJoin();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Слишком много попыток, попробуйте через час",
    );
    expect(window.location.hash).toBe("");
  });

  it.each([
    ["network", new api.ApiError("network", 0)],
    ["5xx", new api.ApiError("http", 503)],
    ["parse", new api.ApiError("parse", 200)],
  ])("asks to retry on %s failure and still clears the token", async (_n, error) => {
    open("#tok");
    m.acceptInvite.mockRejectedValue(error);
    renderJoin();
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось войти");
    expect(window.location.hash).toBe("");
  });

  it("shows the same state without a token and does not call the API", async () => {
    open("");
    m.acceptInvite.mockClear();
    renderJoin();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Попросите взрослого выпустить новую",
    );
    expect(m.acceptInvite).not.toHaveBeenCalled();
  });
});
