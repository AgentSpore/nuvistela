import { useTranslations } from "next-intl";
import { AppNav } from "@/components/app-nav";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { Link } from "@/i18n/navigation";
import { focusRing } from "@/components/styles";
import { BRAND } from "@/lib/config";
import { BeeMark } from "@/components/ui/icons";

export function SiteHeader() {
  const t = useTranslations("nav");
  return (
    <>
      <a
        href="#main"
        className={`sr-only z-50 rounded-lg bg-ink px-4 py-2 font-semibold text-paper focus:not-sr-only focus:fixed focus:left-3 focus:top-3 ${focusRing}`}
      >
        {t("skip")}
      </a>
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-2 px-3 py-3 sm:px-6 sm:py-4">
        <div className="flex min-w-0 items-center gap-1 sm:gap-4">
          <Link
            href="/"
            aria-label={t("home")}
            className={`inline-flex min-h-11 items-center gap-2 rounded-lg pr-1 font-display text-xl font-bold tracking-tight ${focusRing}`}
          >
            <BeeMark />
            <span className="hidden min-[420px]:inline">{BRAND}</span>
          </Link>
          <AppNav />
        </div>
        <LocaleSwitcher />
      </header>
    </>
  );
}
