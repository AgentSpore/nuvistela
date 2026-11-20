import { describe, expect, it } from "vitest";

import en from "../messages/en.json";
import ru from "../messages/ru.json";

const FAMILY_WORDING = /famil|whole|семь|все[йм]? |семейн/i;
const SOLO_HOSTILE = /we did it|мы готовы|сделал\(а\)|we are ready|играете не один/i;

const pick = (m: typeof en | typeof ru) => ({
  adventure: m.adventure,
  nav: m.nav,
  gate: m.gate,
  new: m.new,
  member: m.member,
  join: m.join,
  family: m.family,
  play: m.play,
});

const texts = (node: unknown): string[] =>
  typeof node === "string" ? [node] : Object.values(node as object).flatMap(texts);

describe("player-facing copy", () => {
  it.each([
    ["ru", ru],
    ["en", en],
  ] as const)("does not presume a family or a group (%s)", (_locale, messages) => {
    for (const [section, strings] of Object.entries(pick(messages))) {
      const text = texts(strings).join("\n");
      expect(text, section).not.toMatch(SOLO_HOSTILE);
      expect(text, section).not.toMatch(FAMILY_WORDING);
    }
  });
});
