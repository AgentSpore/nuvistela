import { renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Join } from "@/components/join";
import { FamilyView } from "@/components/family-view";
import { InviteLink } from "@/components/invite-link";
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
  it("offers reissue for others but not for self", async () => {
    renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    const buttons = screen.getAllByRole("button", { name: /Новая ссылка/ });
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAccessibleName("Новая ссылка: Маша");
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

describe("/new", () => {
  it("focuses the first invalid field after a failed submit", async () => {
    renderRu(<NewFamily />);
    await userEvent.click(screen.getByRole("button", { name: "Создать семью" }));
    await waitFor(() => expect(screen.getByLabelText("Название семьи")).toHaveFocus());
  });

  it("keeps the creator's link and shows the add form after creation", async () => {
    m.createFamily.mockResolvedValue({
      family_id: "f1",
      member: member(),
      invite_url: "/api/v1/invite/t1",
    });
    renderRu(<NewFamily />);
    await userEvent.type(screen.getByLabelText("Название семьи"), "Ивановы");
    await userEvent.type(screen.getByLabelText("Ваше имя"), "Анна");
    await userEvent.click(screen.getByRole("button", { name: "Создать семью" }));
    expect(await screen.findByLabelText("Ссылка для входа: Анна")).toHaveValue(
      `${window.location.origin}/api/v1/invite/t1`,
    );
    expect(
      screen.getByRole("heading", { name: "Добавить участника" }),
    ).toBeInTheDocument();
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
  it("shows reissue only on child rows", async () => {
    m.listMembers.mockResolvedValue([
      member(),
      member({ id: "m3", display_name: "Олег" }),
      member({ id: "m2", display_name: "Маша", age_band: "6-9", role: "child" }),
    ]);
    renderRu(<FamilyView />);
    await screen.findByText("Маша", { selector: "p" });
    expect(screen.getAllByRole("button", { name: /Новая ссылка/ })).toHaveLength(1);
  });

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

  it("renders an alert on /family when the roster fails", async () => {
    m.listMembers.mockRejectedValue(new api.ApiError("http", 500));
    renderRu(<FamilyView />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("errors reach assistive tech before focus", () => {
  it("field is already described by its error when it receives focus", async () => {
    renderRu(<NewFamily />);
    const field = screen.getByLabelText("Название семьи");
    let seen: string | null = "unset";
    field.addEventListener(
      "focus",
      () => (seen = field.getAttribute("aria-describedby")),
    );
    await userEvent.click(screen.getByRole("button", { name: "Создать семью" }));
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
    m.acceptInvite.mockResolvedValue(member());
    renderJoin();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/play"));
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
