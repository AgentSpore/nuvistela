import { useTranslations } from "next-intl";
import { BRAND } from "@/lib/config";

export function SiteFooter() {
  const t = useTranslations("landing");
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-1 px-5 py-8 text-sm text-muted sm:flex-row sm:justify-between sm:px-8">
        <p>{t("privacy")}</p>
        <p>© {BRAND}</p>
      </div>
    </footer>
  );
}
