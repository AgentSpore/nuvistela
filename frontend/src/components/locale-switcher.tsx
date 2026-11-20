"use client";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { focusRing } from "@/components/styles";

export function LocaleSwitcher() {
  const t = useTranslations("locale");
  const current = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  return (
    <label className="shrink-0">
      <span className="sr-only">{t("label")}</span>
      <select
        value={current}
        onChange={(event) => {
          const locale = routing.locales.find((item) => item === event.target.value);
          if (locale) router.replace(pathname, { locale });
        }}
        className={`min-h-11 max-w-32 rounded-full border border-line bg-card px-3 text-sm font-semibold text-ink ${focusRing}`}
      >
        {routing.locales.map((locale) => (
          <option key={locale} value={locale} lang={locale}>
            {t(locale)}
          </option>
        ))}
      </select>
    </label>
  );
}
