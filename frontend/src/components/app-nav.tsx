"use client";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { focusRing } from "@/components/styles";

const ITEMS = ["play", "family", "new"] as const;

export function AppNav() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  return (
    <nav aria-label={t("label")}>
      <ul className="flex items-center gap-0.5 sm:gap-1">
        {ITEMS.map((k) => {
          const current = pathname === `/${k}`;
          return (
            <li key={k}>
              <Link
                href={`/${k}`}
                aria-current={current ? "page" : undefined}
                className={`relative inline-flex min-h-11 items-center rounded-lg px-2.5 text-[0.9rem] font-medium text-muted transition-colors duration-150 hover:bg-sunken hover:text-ink aria-[current=page]:text-ink sm:px-3.5 sm:text-base ${focusRing}`}
              >
                {t(k)}
                {current && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-2.5 -bottom-0.5 h-0.5 rounded-full bg-honey-deep sm:inset-x-3.5"
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
