import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Link } from "@/i18n/navigation";
import type { Member } from "@/lib/api";
import type { MeState } from "@/lib/use-me";

type Props = { state: MeState; children: (me: Member) => ReactNode };

/** Renders children only for a logged-in member; otherwise the matching notice. */
export function Gate({ state, children }: Props) {
  const t = useTranslations("gate");
  if (state.status === "ready") return <>{children(state.me)}</>;
  if (state.status === "loading")
    return (
      <p role="status" className="text-muted">
        {t("loading")}
      </p>
    );
  if (state.status === "error")
    return (
      <p role="alert" className="font-medium text-danger">
        {t("error")}
      </p>
    );
  return (
    <div role="status" className="flex flex-col items-start gap-3">
      <p>{t("anonymous")}</p>
      <Link
        href="/new"
        className="font-semibold text-accent underline underline-offset-4"
      >
        {t("create")}
      </Link>
    </div>
  );
}
