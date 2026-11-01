import type { CSSProperties } from "react";

const HUES = [25, 62, 105, 150, 195, 245, 295, 340];

/** Stable hue per member id, so a person keeps one colour on every page. */
export function hueOf(id: string): number {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return HUES[h % HUES.length] ?? 62;
}

type Props = { id: string; name: string; size?: "sm" | "md" };

export function Avatar({ id, name, size = "md" }: Props) {
  const dim = size === "sm" ? "size-8 text-sm" : "size-11 text-lg";
  return (
    <span
      aria-hidden="true"
      style={{ "--h": hueOf(id) } as CSSProperties}
      className={`avatar inline-flex shrink-0 select-none items-center justify-center rounded-full font-display font-semibold ${dim}`}
    >
      {Array.from(name.trim())[0]?.toUpperCase() ?? "?"}
    </span>
  );
}
