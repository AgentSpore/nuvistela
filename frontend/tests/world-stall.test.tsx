import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import * as api from "@/lib/api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));

const adventure = {
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

/** The adventure answers; the world request never does, until its own abort signal fires. */
function stallWorld(url: string, init?: RequestInit): Promise<Response> {
  if (!url.endsWith("/adventure")) {
    return new Promise((_, reject) =>
      init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))),
    );
  }
  return Promise.resolve(new Response(JSON.stringify(adventure)));
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(api.getMe).mockResolvedValue(member());
  vi.stubGlobal("fetch", vi.fn(stallWorld));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("a world request that never answers stops holding the quest back after the read timeout", async () => {
  renderRu(<Adventure />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(7_000);
  });
  expect(screen.queryByText("Найти ключ от маяка")).toBeNull();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(20_000);
  });
  expect(screen.getByText("Найти ключ от маяка")).toBeInTheDocument();
});
