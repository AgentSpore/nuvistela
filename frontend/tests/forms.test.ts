import { describe, expect, it } from "vitest";
import { check, familySchema, memberSchema, parseInterests } from "@/lib/forms";

describe("parseInterests", () => {
  it("splits on commas, trims, drops blanks", () => {
    expect(parseInterests(" lego, , space ,")).toEqual(["lego", "space"]);
  });
});

describe("family form", () => {
  it("accepts valid input and trims", () => {
    const r = check(familySchema, {
      title: " Ivanovs ",
      display_name: "Anna",
      interests: [],
    });
    expect(r).toEqual({
      ok: true,
      data: { title: "Ivanovs", display_name: "Anna", interests: [] },
    });
  });
  it("flags blank title and more than 10 interests", () => {
    const tags = Array.from({ length: 11 }, (_, i) => `t${i}`);
    const r = check(familySchema, { title: "  ", display_name: "A", interests: tags });
    expect(r).toEqual({ ok: false, errors: { title: "required", interests: "tooMany" } });
  });
});

describe("member form", () => {
  const base = { display_name: "Kid", interests: [] };
  it("rejects adult role with child band", () => {
    const r = check(memberSchema, { ...base, age_band: "6-9", role: "adult" });
    expect(r).toEqual({ ok: false, errors: { role: "roleMismatch" } });
  });
  it("rejects child role with adult band", () => {
    expect(check(memberSchema, { ...base, age_band: "adult", role: "child" }).ok).toBe(
      false,
    );
  });
  it("accepts child 6-9", () => {
    expect(check(memberSchema, { ...base, age_band: "6-9", role: "child" }).ok).toBe(
      true,
    );
  });
});
