import { describe, expect, it } from "vitest";
import { adventureSchema } from "@/lib/adventure-api";

const base = { world: null, quest: null, chapters: [] };

describe("adventure schema: chronicle and skills", () => {
  it("falls back to empty for an unreadable chronicle and leaves absent skills undefined", () => {
    const got = adventureSchema.parse({ ...base, chronicle: [{ chapter: "x" }] });
    expect(got.chronicle).toEqual([]);
    expect(got.skills).toBeUndefined();
  });
  it("reads well-formed fields", () => {
    const got = adventureSchema.parse({
      ...base,
      chronicle: [{ chapter: 2, text: "Зажёгся маяк" }],
      skills: ["смелость"],
    });
    expect(got.chronicle).toEqual([{ chapter: 2, text: "Зажёгся маяк" }]);
    expect(got.skills).toEqual(["смелость"]);
  });
});
