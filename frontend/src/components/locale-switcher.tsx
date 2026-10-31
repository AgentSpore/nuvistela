"use client";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

export function LocaleSwitcher() {
  const t = useTranslations("locale");
  const current = useLocale();
  const pathname = usePathname();
  return (
    <nav aria-label={t("label")} className="flex gap-1 text-sm">
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href={pathname}
          locale={locale}
          lang={locale}
          aria-current={locale === current ? "true" : undefined}
          className="rounded px-2 py-2 text-ink underline-offset-4 hover:underline aria-[current=true]:font-bold"
        >
          {t(locale)}
        </Link>
      ))}
    </nav>
  );
}
