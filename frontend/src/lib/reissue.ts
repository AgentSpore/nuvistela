import type { Member } from "@/lib/api";

/**
 * Who may reissue whose link: the owner anyone's; another adult only a child's or their own;
 * a child nobody's.
 */
export function canReissue(me: Member, target: Member): boolean {
  if (me.role !== "adult") return false;
  if (me.is_owner) return true;
  return target.role === "child" || target.id === me.id;
}
