import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { focusRing } from "@/components/styles";
import { BRAND } from "@/lib/config";
import { BeeMark } from "@/components/ui/icons";

export function HomeLink() {
  const t = useTranslations("nav");
  return (
    <Link
      href="/"
      aria-label={t("home")}
      className={`inline-flex min-h-11 items-center gap-2 rounded-lg pr-1 font-display text-xl font-bold tracking-tight ${focusRing}`}
    >
      <BeeMark />
      <span className="hidden min-[420px]:inline">{BRAND}</span>
    </Link>
  );
}
