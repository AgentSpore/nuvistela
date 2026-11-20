import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdventureStart } from "@/components/adventure-start";
import * as adv from "@/lib/adventure-api";
import { ApiError } from "@/lib/api";
import en from "../messages/en.json";
import ru from "../messages/ru.json";
import { renderRu } from "./render";

vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  startAdventure: vi.fn(),
  getAdventure: vi.fn(),
  getWorld: vi.fn(),
}));
const start = vi.mocked(adv.startAdventure);
const onStarted = vi.fn();

const field = () => screen.getByLabelText("Опишите свой мир");
const go = () => userEvent.click(screen.getByRole("button", { name: "Начать" }));

beforeEach(() => {
  vi.clearAllMocks();
  start.mockResolvedValue({ world_status: "pending", quest: null });
  vi.mocked(adv.getAdventure).mockResolvedValue({
    world: null,
    quest: null,
    chapters: [],
  });
  vi.mocked(adv.getWorld).mockRejectedValue(new Error("no world yet"));
});

describe("own world is the main path", () => {
  it("shows the description field first and presets below it", () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    const presets = screen.getByRole("group", { name: "или выберите готовый" });
    expect(
      field().compareDocumentPosition(presets) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.queryByRole("radio", { name: "Свой мир" })).toBeNull();
    expect(screen.getByRole("button", { name: "Начать" })).toBeDisabled();
  });

  it("sends custom genre with the trimmed text", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.type(field(), "  Город в облаках ");
    await go();
    expect(start).toHaveBeenCalledWith("f1", "custom", "Город в облаках");
    expect(onStarted).toHaveBeenCalledWith("mine");
  });

  it("sends only the preset when it is chosen, dropping typed text", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.type(field(), "что-то");
    await userEvent.click(screen.getByRole("radio", { name: "Космос" }));
    expect(field()).toHaveValue("");
    await go();
    expect(start).toHaveBeenCalledWith("f1", "space");
  });

  it("typing after a preset deselects it", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.click(screen.getByRole("radio", { name: "Пираты" }));
    await userEvent.type(field(), "а");
    expect(screen.getByRole("radio", { name: "Пираты" })).not.toBeChecked();
    await go();
    expect(start).toHaveBeenCalledWith("f1", "custom", "а");
  });
});

describe("examples, counter, limit", () => {
  it("tapping an example fills the field", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.click(
      screen.getByRole("button", { name: ru.adventure.examples.two }),
    );
    expect(field()).toHaveValue(ru.adventure.examples.two);
    expect(field()).toHaveFocus();
  });

  it("has 4 examples per language, each within the limit", () => {
    for (const m of [ru, en]) {
      const list = Object.values(m.adventure.examples);
      expect(list).toHaveLength(4);
      for (const text of list) expect(text.length).toBeLessThanOrEqual(300);
    }
  });

  it("shows a live counter and caps input at 300", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    expect(screen.getByText("0 из 300")).toBeInTheDocument();
    await userEvent.click(field());
    await userEvent.paste("я".repeat(320));
    expect(screen.getByText("300 из 300")).toBeInTheDocument();
    expect(field()).toHaveAttribute("maxlength", "300");
  });

  it("gives the counter a spoken label and announces it only near the limit", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    const live = () => screen.getByText("Символов: 0 из 300").closest("p");
    expect(live()).toHaveAttribute("aria-live", "off");
    await userEvent.click(field());
    await userEvent.paste("я".repeat(280));
    expect(screen.getByText("Символов: 280 из 300").closest("p")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });

  it("explains a 422 inline next to the field", async () => {
    start.mockRejectedValue(new ApiError("http", 422));
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.type(field(), "мир");
    await go();
    const msg = await screen.findByText(/длиннее 300 знаков/);
    expect(field()).toHaveAccessibleDescription(
      expect.stringContaining(msg.textContent ?? ""),
    );
    expect(field()).toBeInvalid();
    expect(screen.getByRole("alert")).toBe(msg);
    expect(field()).toHaveFocus();
    expect(onStarted).not.toHaveBeenCalled();
  });

  it("keeps a generic alert for other failures", async () => {
    start.mockRejectedValue(new ApiError("network", 0));
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.type(field(), "мир");
    await go();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("pre-start read", () => {
  it("is bounded by the world read timeout, so a stalled read cannot hold the start", async () => {
    renderRu(<AdventureStart familyId="f1" onStarted={onStarted} onPoll={vi.fn()} />);
    await userEvent.type(field(), "мир");
    await go();
    expect(adv.getAdventure).toHaveBeenCalledWith("f1", adv.WORLD_READ_TIMEOUT_MS);
  });
});
