"use client";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { focusRing } from "@/components/styles";

export function LocaleSwitcher() {
  const t = useTranslations("locale");
  const current = useLocale();
  const pathname = usePathname();
  return (
    <nav
      aria-label={t("label")}
      className="flex rounded-full border border-line bg-card p-0.5"
    >
      {routing.locales.map((locale) => (
        <Link
          key={locale}
          href={pathname}
          locale={locale}
          lang={locale}
          hrefLang={locale}
          aria-current={locale === current ? "true" : undefined}
          aria-label={`${locale.toUpperCase()}, ${t(locale)}`}
          className={`inline-flex min-h-10 min-w-10 items-center justify-center rounded-full px-2 text-sm font-semibold uppercase text-muted transition-colors duration-150 hover:text-ink aria-[current=true]:bg-honey aria-[current=true]:text-honey-ink ${focusRing}`}
        >
          <span aria-hidden="true">{locale}</span>
        </Link>
      ))}
    </nav>
  );
}
