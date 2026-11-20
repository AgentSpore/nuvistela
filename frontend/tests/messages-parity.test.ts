import { describe, expect, it } from "vitest";
import en from "../messages/en.json";
import es from "../messages/es.json";
import ru from "../messages/ru.json";
import zh from "../messages/zh-CN.json";

type Leaves = Map<string, string>;

function leaves(node: unknown, path = "", out: Leaves = new Map()): Leaves {
  if (typeof node === "string") out.set(path, node);
  else if (Array.isArray(node))
    node.forEach((item, i) => leaves(item, `${path}[${i}]`, out));
  else if (node && typeof node === "object")
    for (const [key, value] of Object.entries(node))
      leaves(value, path ? `${path}.${key}` : key, out);
  return out;
}

/** Argument names inside `{...}` at any nesting depth, ignoring plural/select branch text. */
function placeholders(text: string): string[] {
  const names = new Set<string>();
  const scan = (s: string) => {
    let i = 0;
    while (i < s.length) {
      if (s[i] !== "{") {
        i++;
        continue;
      }
      let depth = 1;
      let j = i + 1;
      while (j < s.length && depth > 0) {
        depth += s[j] === "{" ? 1 : s[j] === "}" ? -1 : 0;
        j++;
      }
      const body = s.slice(i + 1, j - 1);
      const name = body.split(",")[0]?.trim() ?? "";
      if (/^\w+$/.test(name)) names.add(name);
      const comma = body.indexOf(",");
      if (comma >= 0) scan(body.slice(body.indexOf(",", comma + 1) + 1));
      i = j;
    }
  };
  scan(text);
  return [...names].sort();
}

const reference = leaves(en);
const locales = { ru, es, "zh-CN": zh };

describe.each(Object.entries(locales))(
  "messages/%s.json parity with en",
  (_name, messages) => {
    const own = leaves(messages);
    it("has the same keys", () => {
      const missing = [...reference.keys()].filter((k) => !own.has(k));
      const extra = [...own.keys()].filter((k) => !reference.has(k));
      expect({ missing, extra }).toEqual({ missing: [], extra: [] });
    });
    it("uses the same ICU placeholders", () => {
      const differ = [...reference].flatMap(([key, text]) => {
        const mine = own.get(key);
        if (mine === undefined) return [];
        const a = placeholders(text).join();
        const b = placeholders(mine).join();
        return a === b ? [] : [`${key}: ${a} != ${b}`];
      });
      expect(differ).toEqual([]);
    });
    it("has no empty strings", () => {
      expect([...own].filter(([, v]) => v.trim() === "").map(([k]) => k)).toEqual([]);
    });
  },
);

describe("plural categories", () => {
  it("es plurals carry one and other; zh-CN other only", () => {
    const plural = (text: string) =>
      [...text.matchAll(/\b(zero|one|two|few|many|other) \{/g)].map((m) => m[1]);
    const key = "family.subtitle";
    expect(plural(leaves(es).get(key) ?? "")).toEqual(["one", "other"]);
    expect(plural(leaves(zh).get(key) ?? "")).toEqual(["other"]);
  });
});
