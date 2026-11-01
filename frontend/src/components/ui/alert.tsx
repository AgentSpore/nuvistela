import type { ReactNode } from "react";
import { AlertIcon, InfoIcon, CheckIcon } from "@/components/ui/icons";

export type Tone = "danger" | "info" | "ok";

const TONE: Record<Tone, { box: string; icon: ReactNode }> = {
  danger: {
    box: "border-danger/40 bg-danger-soft text-ink [&_svg]:text-danger",
    icon: <AlertIcon />,
  },
  info: {
    box: "border-honey-deep/50 bg-honey-soft text-ink [&_svg]:text-ink",
    icon: <InfoIcon />,
  },
  ok: { box: "border-ok/40 bg-ok-soft text-ink [&_svg]:text-ok", icon: <CheckIcon /> },
};

type Props = { tone?: Tone; title?: string; children?: ReactNode; action?: ReactNode };

/** Inline notice. Danger interrupts screen readers (alert), the rest wait politely (status). */
export function Alert({ tone = "danger", title, children, action }: Props) {
  const t = TONE[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`rise flex gap-3 rounded-2xl border px-4 py-3.5 ${t.box}`}
    >
      <span className="mt-0.5 shrink-0">{t.icon}</span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <p className={title ? "text-muted" : ""}>{children}</p>}
        {action && <div className="mt-2.5">{action}</div>}
      </div>
    </div>
  );
}
