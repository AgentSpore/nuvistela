import { useTranslations } from "next-intl";
import { focusRing } from "@/components/styles";

/** First tab stop: jumps over the header to the page's `<main id="main">`. */
export function SkipLink() {
  const t = useTranslations("nav");
  return (
    <a
      href="#main"
      className={`sr-only z-50 rounded-lg bg-ink px-4 py-2 font-semibold text-paper focus:not-sr-only focus:fixed focus:left-3 focus:top-3 ${focusRing}`}
    >
      {t("skip")}
    </a>
  );
}
