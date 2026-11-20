import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QuestCard } from "@/components/quest-card";
import type { Quest } from "@/lib/adventure-api";
import { renderRu } from "./render";

const quest: Quest = {
  id: "q1",
  seq: 1,
  title: "Найти маяк",
  description: "Дойдите до маяка.",
  skill: "наблюдательность",
  source: "model",
  status: "open",
};

let report: (ratio: number) => void = () => {};
beforeEach(() => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: (e: { intersectionRatio: number }[]) => void) {
        report = (ratio) => cb([{ intersectionRatio: ratio }]);
      }
      observe() {}
      disconnect() {}
    },
  );
  HTMLDialogElement.prototype.showModal ??= function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => vi.unstubAllGlobals());

const bar = () => screen.queryByTestId("quest-action-bar");

describe("quest action bar", () => {
  it("is not rendered before the observer reports, nor while the card button is fully visible", () => {
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    expect(bar()).toBeNull();
    act(() => report(1));
    expect(bar()).toBeNull();
    expect(screen.getAllByRole("button", { name: "Готово!" })).toHaveLength(1);
  });

  it("appears when the button leaves the viewport, also when only partly visible, and goes away again", () => {
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    act(() => report(0));
    expect(bar()).not.toBeNull();
    act(() => report(1));
    expect(bar()).toBeNull();
    act(() => report(0.5));
    expect(bar()).not.toBeNull();
  });

  it("opens the same sheet as the card button", async () => {
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    act(() => report(0));
    await userEvent.click(bar()!.querySelector("button")!);
    expect(
      await screen.findByLabelText(/заметк|отметк/i, {}, { timeout: 2000 }),
    ).toBeTruthy();
  });

  it("returns focus to the bar button that opened the sheet", async () => {
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    act(() => report(0));
    const opener = bar()!.querySelector("button")!;
    await userEvent.click(opener);
    await userEvent.click(await screen.findByRole("button", { name: "Закрыть" }));
    expect(opener).toHaveFocus();
  });

  it("returns focus to the card button when that one opened the sheet", async () => {
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    const card = screen.getByRole("button", { name: "Готово!" });
    await userEvent.click(card);
    await userEvent.click(await screen.findByRole("button", { name: "Закрыть" }));
    expect(card).toHaveFocus();
  });

  it("moves focus to the card button when the bar goes away while holding focus", () => {
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    act(() => report(0));
    act(() => bar()!.querySelector("button")!.focus());
    act(() => report(1));
    expect(bar()).toBeNull();
    expect(screen.getByRole("button", { name: "Готово!" })).toHaveFocus();
  });

  it("is never rendered without an observer", () => {
    vi.unstubAllGlobals();
    renderRu(<QuestCard quest={quest} onDone={() => {}} />);
    expect(bar()).toBeNull();
  });
});
