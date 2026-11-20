import { screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import * as api from "@/lib/api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));

const payload = {
  world: { status: "ready" },
  quest: {
    id: "q1",
    seq: 1,
    title: "Найти ключ от маяка",
    description: "Поищите дома что-нибудь, похожее на ключ.",
    skill: "наблюдательность",
    source: "world",
    status: "open",
  },
  chapters: [],
};

beforeEach(() => {
  vi.mocked(api.getMe).mockResolvedValue(member());
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))),
  );
});
afterEach(() => vi.unstubAllGlobals());

it("shows quest 1 of a generated world instead of the load error", async () => {
  renderRu(<Adventure />);
  expect(await screen.findByText("Найти ключ от маяка")).toBeInTheDocument();
  expect(
    screen.getByText("Поищите дома что-нибудь, похожее на ключ."),
  ).toBeInTheDocument();
});
