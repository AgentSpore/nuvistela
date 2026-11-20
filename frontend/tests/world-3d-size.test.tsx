import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import * as api from "@/lib/api";
import * as adv from "@/lib/adventure-api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
  getWorld: vi.fn(),
}));
vi.mock("@/lib/world-3d-viewer", () => ({
  startViewer: vi.fn(() => new Promise(() => {})),
}));
const a = vi.mocked(adv);

const hex = (c: string) => c.repeat(64);
const OWN = {
  status: "ready",
  url: `/api/v1/media/${hex("d")}.spz`,
  panorama_url: `/api/v1/media/pano/${hex("d")}.webp`,
};
const megabytes = (text: string) => Number(/(\d+) МБ/.exec(text)?.[1]);

function show(genre: string, scene: unknown) {
  a.getAdventure.mockResolvedValue({
    world: { status: "ready" },
    quest: null,
    chapters: [],
  } as unknown as adv.Adventure);
  a.getWorld.mockResolvedValue({
    status: "ready",
    genre,
    cover: { status: "ready", url: `/api/v1/media/${hex("a")}.webp` },
    scene,
    world: {
      title: "Маяк",
      setting: "Море.",
      prologue: "Привет.",
      locations: [],
      heroes: [],
    },
  } as unknown as adv.WorldResponse);
  renderRu(<Adventure />);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMe).mockResolvedValue(member());
});

describe("size of the 3D walk", () => {
  it.each(["pirates", "fairy_tale", "custom"])(
    "%s: with the family's own scene ready both buttons say the same ceiling",
    async (genre) => {
      show(genre, OWN);
      const corner = await screen.findByRole("button", { name: /в 3D, до \d+ МБ/ });
      const about = screen.getByText("О мире").closest("details") as HTMLElement;
      const text = within(about).getByRole("button", { name: /· до \d+ МБ/, hidden: true });
      expect(megabytes(corner.getAttribute("aria-label") ?? "")).toBe(
        megabytes(text.textContent ?? ""),
      );
    },
  );

  it("a library world shows its exact size, no ceiling", async () => {
    show("pirates", null);
    await screen.findByText("О мире");
    expect(
      screen.getByRole("button", { name: "Пройтись по миру · 7 МБ", hidden: true }),
    ).toBeInTheDocument();
  });
});
