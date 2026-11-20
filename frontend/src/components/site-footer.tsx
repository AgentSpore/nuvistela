import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { BRAND } from "@/lib/config";

export function SiteFooter() {
  const t = useTranslations("landing");
  const tf = useTranslations("footer");
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-1 px-5 py-8 text-sm text-muted sm:flex-row sm:justify-between sm:px-8">
        <p>{t("privacy")}</p>
        <Link href="/privacy" className="underline underline-offset-2 hover:text-ink">
          {tf("privacy")}
        </Link>
        <p>© {BRAND}</p>
      </div>
      <p className="mx-auto w-full max-w-5xl px-5 pb-6 text-sm text-muted sm:px-8">
        {t("languageScope")}
      </p>
    </footer>
  );
}
