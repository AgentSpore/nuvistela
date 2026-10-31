import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

export function LocaleSwitcher() {
  const t = useTranslations("locale");
  const current = useLocale();
  return (
    <nav aria-label={t("label")} className="absolute top-4 right-4 flex gap-3 text-sm">
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href="/"
          locale={locale}
          lang={locale}
          aria-current={locale === current ? "true" : undefined}
          className="rounded px-2 py-1 text-ink underline-offset-4 hover:underline aria-[current=true]:font-bold"
        >
          {t(locale)}
        </Link>
      ))}
    </nav>
  );
}
