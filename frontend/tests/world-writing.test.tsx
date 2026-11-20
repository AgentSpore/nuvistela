import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorldWriting, WRITING_STEP_MS } from "@/components/world-writing";
import { saveWorldChoice } from "@/lib/world-choice";
import { renderRu } from "./render";

const reduced = (on: boolean) =>
  vi.stubGlobal(
    "matchMedia",
    vi.fn((q: string) => ({ matches: on && q.includes("reduce"), media: q })),
  );
const current = () => document.querySelector("[aria-current='step']");

beforeEach(() => {
  sessionStorage.clear();
  reduced(false);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("world writing", () => {
  it("quotes the description the player typed, with all three steps", () => {
    saveWorldChoice("f1", { kind: "text", text: "Город в облаках" });
    renderRu(<WorldWriting familyId="f1" />);
    expect(screen.getByText("Мир пишется")).toBeVisible();
    expect(screen.getByText("Город в облаках")).toBeVisible();
    for (const s of ["Придумываем места", "Выбираем героев", "Готовим первое задание"])
      expect(screen.getByText(s)).toBeVisible();
    expect(screen.getByText(/Можно закрыть|Её можно закрыть/)).toBeVisible();
  });

  it("names a chosen preset instead of a quote", () => {
    saveWorldChoice("f1", { kind: "genre", genre: "space" });
    renderRu(<WorldWriting familyId="f1" />);
    expect(screen.getByText("Космос")).toBeVisible();
  });

  it("ignores a remembered genre that is not one of ours", () => {
    sessionStorage.setItem(
      "bumbli.worldChoice.f1",
      JSON.stringify({ genre: "<b>x</b>" }),
    );
    renderRu(<WorldWriting familyId="f1" />);
    expect(screen.queryByRole("blockquote")).toBeNull();
    expect(document.body.innerHTML).not.toContain("<b>x</b>");
  });

  it("has no quote when nothing is remembered", () => {
    renderRu(<WorldWriting familyId="f1" />);
    expect(screen.queryByRole("blockquote")).toBeNull();
  });

  it("moves to the next step on a timer and holds on the last", () => {
    renderRu(<WorldWriting familyId="f1" />);
    expect(current()).toHaveTextContent("Придумываем места");
    act(() => vi.advanceTimersByTime(WRITING_STEP_MS));
    expect(current()).toHaveTextContent("Выбираем героев");
    act(() => vi.advanceTimersByTime(WRITING_STEP_MS));
    expect(current()).toHaveTextContent("Готовим первое задание");
    act(() => vi.advanceTimersByTime(WRITING_STEP_MS * 5));
    expect(current()).toHaveTextContent("Готовим первое задание");
  });

  it("marks passed steps with a check and none at the start", () => {
    const { container } = renderRu(<WorldWriting familyId="f1" />);
    expect(container.textContent).not.toContain("✓");
    act(() => vi.advanceTimersByTime(WRITING_STEP_MS));
    act(() => vi.advanceTimersByTime(WRITING_STEP_MS));
    expect(container.textContent?.match(/✓/g)).toHaveLength(2);
  });

  it("paints the chosen preset's colours, the neutral palette otherwise", () => {
    const bg = (c: HTMLElement) =>
      c.querySelector<HTMLElement>("[style*='gradient']")?.style.backgroundImage;
    saveWorldChoice("f1", { kind: "genre", genre: "space" });
    const space = renderRu(<WorldWriting familyId="f1" />);
    expect(bg(space.container)).toContain("oklch(0.3 0.1 275)");
    space.unmount();
    sessionStorage.clear();
    const neutral = renderRu(<WorldWriting familyId="f1" />);
    expect(bg(neutral.container)).toContain("oklch(0.93 0.05 90)");
  });

  it("under reduced motion shows every step, static and unmarked", () => {
    reduced(true);
    const { container } = renderRu(<WorldWriting familyId="f1" />);
    expect(screen.getByText("Придумываем места")).toBeVisible();
    expect(screen.getByText("Готовим первое задание")).toBeVisible();
    act(() => vi.advanceTimersByTime(WRITING_STEP_MS * 3));
    expect(current()).toBeNull();
    expect(container.querySelector("[class*='animate-']")?.className).toContain(
      "motion-safe:animate-",
    );
  });
});
