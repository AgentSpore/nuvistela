"use client";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { focusRing } from "@/components/styles";

const ITEMS = ["play", "adventure", "family"] as const;

/** A rare action stays reachable without taking a tab: a disclosure that an outside tap, Escape or its own link closes. */
function MoreMenu() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  // Open only for the route it was opened on: back navigation or a locale switch closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!(e.target instanceof Node && menu.current?.contains(e.target)))
        setOpenOn(null);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpenOn(null);
      menu.current?.querySelector("button")?.focus();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  const close = () => setOpenOn(null);
  return (
    <div ref={menu} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="more-menu"
        onClick={() => setOpenOn(open ? null : pathname)}
        className={`inline-flex min-h-11 items-center rounded-lg px-2 text-[0.875rem] font-medium whitespace-nowrap text-muted hover:bg-sunken hover:text-ink sm:px-3.5 sm:text-base ${focusRing}`}
      >
        {t("more")}
      </button>
      {open && (
        <div
          id="more-menu"
          className="absolute right-0 z-20 mt-1 min-w-40 rounded-xl border border-line bg-card p-1 shadow-soft"
        >
          <Link
            href="/new"
            onClick={close}
            className={`flex min-h-11 items-center rounded-lg px-3 whitespace-nowrap text-ink hover:bg-sunken ${focusRing}`}
          >
            {t("new")}
          </Link>
        </div>
      )}
    </div>
  );
}

export function AppNav() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  return (
    <nav
      aria-label={t("label")}
      className="order-last flex w-full items-center justify-between sm:order-none sm:w-auto sm:gap-1"
    >
      <ul className="flex flex-wrap items-center gap-0.5 sm:gap-1">
        {ITEMS.map((k) => {
          const current = pathname === `/${k}`;
          return (
            <li key={k}>
              <Link
                href={`/${k}`}
                aria-current={current ? "page" : undefined}
                className={`relative inline-flex min-h-11 items-center rounded-lg px-2 text-[0.875rem] whitespace-nowrap font-medium text-muted transition-colors duration-150 hover:bg-sunken hover:text-ink aria-[current=page]:text-ink sm:px-3.5 sm:text-base ${focusRing}`}
              >
                {t(k)}
                {current && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-honey-deep sm:inset-x-3.5"
                  />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
      <MoreMenu />
    </nav>
  );
}
