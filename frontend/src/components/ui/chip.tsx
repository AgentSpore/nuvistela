import type { ReactNode } from "react";

type Props = { children: ReactNode; tone?: "neutral" | "honey" };

export function Chip({ children, tone = "neutral" }: Props) {
  const cls =
    tone === "honey"
      ? "bg-honey-soft text-ink border-honey-deep/50"
      : "bg-sunken text-muted border-line";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-sm font-medium ${cls}`}
    >
      {children}
    </span>
  );
}
