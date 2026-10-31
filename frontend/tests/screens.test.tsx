import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FamilyView } from "@/components/family-view";
import { InviteLink } from "@/components/invite-link";
import { NewFamily } from "@/components/new-family";
import { Play } from "@/components/play";
import * as api from "@/lib/api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
  listMembers: vi.fn(),
  sendAgentMessage: vi.fn(),
  createFamily: vi.fn(),
  reissueInvite: vi.fn(),
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
