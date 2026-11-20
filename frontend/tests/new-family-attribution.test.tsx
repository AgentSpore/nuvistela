import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewFamily } from "@/components/new-family";
import { member, renderRu } from "./render";

vi.mock("@/i18n/navigation", async (orig) => ({
  ...(await orig<typeof import("@/i18n/navigation")>()),
  useRouter: () => ({ replace: vi.fn() }),
}));
const fetchMock = vi.fn();
const SESSION = {
  session_id: "6f1c1d1e-2b3a-4c5d-8e9f-0a1b2c3d4e5f",
  source: "telegram",
};

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.setItem("bumbli-pilot-session", JSON.stringify(SESSION));
  history.replaceState(null, "", "/new");
});
afterEach(() => {
  fetchMock.mockReset();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe("/new pilot attribution", () => {
  it("sends the landing session's first-touch source with the new game", async () => {
    const created = { family_id: "f1", member: member(), invite_url: "/join#t1" };
    fetchMock.mockResolvedValue(new Response(JSON.stringify(created), { status: 201 }));
    renderRu(<NewFamily />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Название игры"), "Ивановы");
    await user.type(screen.getByLabelText("Ваше имя"), "Анна");
    await user.click(
      screen.getByRole("checkbox", { name: /Я родитель или законный представитель/ }),
    );
    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    await screen.findByRole("link", { name: "Перейти к игре" });
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.attribution).toEqual({ ...SESSION, intent: null });
  });
});
