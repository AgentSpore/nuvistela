import { z } from "zod";
import { memberSchema, type Member } from "@/lib/api";

const KEY = "bumbli.roster";
const rosterSchema = z.array(memberSchema);

/**
 * The API has no "list members" endpoint yet, so members created from this
 * browser are remembered locally. Replace with the server list when it exists.
 */
export function loadRoster(): Member[] {
  try {
    const parsed = rosterSchema.safeParse(
      JSON.parse(localStorage.getItem(KEY) ?? "null"),
    );
    return parsed.success ? parsed.data : [];
  } catch {
    return [];
  }
}

export function rememberMembers(added: Member[]): void {
  const byId = new Map(loadRoster().map((m) => [m.id, m]));
  for (const m of added) byId.set(m.id, m);
  localStorage.setItem(KEY, JSON.stringify([...byId.values()]));
}

export function familyRoster(me: Member): Member[] {
  const others = loadRoster().filter(
    (m) => m.family_id === me.family_id && m.id !== me.id,
  );
  return [me, ...others];
}
