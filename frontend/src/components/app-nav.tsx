import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { focusRing } from "@/components/styles";

const ITEMS = ["new", "play", "family"] as const;

export function AppNav() {
  const t = useTranslations("nav");
  return (
    <nav aria-label={t("label")} className="flex gap-1 text-sm sm:text-base">
      {ITEMS.map((k) => (
        <Link
          key={k}
          href={`/${k}`}
          className={`rounded px-2 py-2 font-medium underline-offset-4 hover:underline ${focusRing}`}
        >
          {t(k)}
        </Link>
      ))}
    </nav>
  );
}
