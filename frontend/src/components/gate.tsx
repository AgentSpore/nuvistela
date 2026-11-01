import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Link } from "@/i18n/navigation";
import type { Member } from "@/lib/api";
import type { MeState } from "@/lib/use-me";
import { Alert } from "@/components/ui/alert";
import { buttonClass } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type Props = { state: MeState; children: (me: Member) => ReactNode };

function Loading({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-4 pt-4">
      <Skeleton className="h-9 w-48" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

function Anonymous() {
  const t = useTranslations("gate");
  return (
    <div
      role="status"
      className="mx-auto mt-6 max-w-md rounded-3xl border border-line bg-card p-7 text-center shadow-soft sm:mt-14 sm:p-9"
    >
      <h1 className="font-display text-2xl font-semibold">{t("anonymousTitle")}</h1>
      <p className="mt-2 text-muted">{t("anonymous")}</p>
      <p className="mt-1 text-sm text-muted">{t("anonymousHint")}</p>
      <Link href="/new" className={buttonClass("primary", "mt-6")}>
        {t("create")}
      </Link>
    </div>
  );
}

/** Renders children only for a logged-in member; otherwise the matching notice. */
export function Gate({ state, children }: Props) {
  const t = useTranslations("gate");
  if (state.status === "ready") return <>{children(state.me)}</>;
  if (state.status === "loading") return <Loading label={t("loading")} />;
  if (state.status === "error")
    return (
      <div className="mt-6">
        <Alert title={t("errorTitle")}>{t("error")}</Alert>
      </div>
    );
  return <Anonymous />;
}
