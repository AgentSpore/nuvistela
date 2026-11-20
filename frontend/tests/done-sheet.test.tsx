import { readFileSync } from "node:fs";
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RewardCard } from "@/components/done-sheet";
import { renderRu } from "./render";

const reduced = (matches: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({ matches, media: q }));

const card = (reaction: string | null = "Маяк вспыхнул ярче.") =>
  renderRu(<RewardCard title="Найти маяк" skill="смелость" height={320} reaction={reaction} />);

afterEach(() => vi.unstubAllGlobals());

describe("celebration on «Готово!»", () => {
  it("bursts honey sparks around a check that pops, and lights the world's line", () => {
    reduced(false);
    card();
    const party = screen.getByTestId("celebration");
    expect(party).toHaveAttribute("aria-hidden", "true");
    expect(party).toHaveAttribute("data-motion", "burst");
    const sparks = party.querySelectorAll(".spark");
    expect(sparks.length).toBeGreaterThanOrEqual(8);
    // every spark flies its own way: no two share an angle
    const angles = new Set([...sparks].map((s) => (s as HTMLElement).style.getPropertyValue("--a")));
    expect(angles.size).toBe(sparks.length);
    expect(party.querySelector("svg")).toHaveClass("pop");
    expect(screen.getByText("Маяк вспыхнул ярче.")).toHaveClass("glow-line");
  });

  it("overlays the card without taking room, so nothing below moves", () => {
    reduced(false);
    card();
    for (const s of screen.getByTestId("celebration").querySelectorAll(".spark, .burst-ring"))
      expect(s).toHaveClass("absolute", "pointer-events-none");
  });

  it("celebrates also without a reaction from the world", () => {
    reduced(false);
    card(null);
    expect(screen.getByTestId("celebration").querySelectorAll(".spark").length).toBeGreaterThan(0);
  });

  it("stays still and only glows softly when the reader asked for less motion", () => {
    reduced(true);
    card();
    const party = screen.getByTestId("celebration");
    expect(party).toHaveAttribute("data-motion", "calm");
    expect(party.querySelectorAll(".spark, .burst-ring")).toHaveLength(0);
    expect(party.querySelector("svg")).not.toHaveClass("pop");
    expect(party.querySelector(".halo")).not.toBeNull();
    expect(screen.getByText("Маяк вспыхнул ярче.")).not.toHaveClass("glow-line");
  });

  it("keeps the reaction line's rise entrance under the glow", () => {
    // jsdom applies no CSS: read the rule itself. One `animation` shorthand replaces the other.
    const css = readFileSync("src/app/globals.css", "utf8");
    const rule = css.match(/\.glow-line\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/animation:[^;]*\brise\b[^;]*,[^;]*\bglow-line\b/);
  });
});
