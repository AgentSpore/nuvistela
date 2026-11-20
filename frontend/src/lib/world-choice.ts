import { GENRES, type Genre } from "@/lib/adventure-api";

/** What this browser chose for the world: kept only to quote it while the world is written. */
export type WorldChoice =
  { kind: "text"; text: string } | { kind: "genre"; genre: Genre };

const key = (familyId: string) => `bumbli.worldChoice.${familyId}`;

export function saveWorldChoice(familyId: string, choice: WorldChoice): void {
  try {
    sessionStorage.setItem(key(familyId), JSON.stringify(choice));
  } catch {
    // Storage may be unavailable: the wait then simply has no quote.
  }
}

export function readWorldChoice(familyId: string): WorldChoice | null {
  try {
    const raw = sessionStorage.getItem(key(familyId));
    const v: unknown = raw ? JSON.parse(raw) : null;
    if (typeof v !== "object" || v === null) return null;
    if ("text" in v && typeof v.text === "string" && v.text)
      return { kind: "text", text: v.text };
    const genre = GENRES.find((g) => "genre" in v && g === v.genre);
    return genre ? { kind: "genre", genre } : null;
  } catch {
    return null;
  }
}

export function clearWorldChoice(familyId: string): void {
  try {
    sessionStorage.removeItem(key(familyId));
  } catch {
    // Nothing stored, nothing to clear.
  }
}
