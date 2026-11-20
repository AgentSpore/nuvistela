import { HeaderNav } from "@/components/header-nav";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { HomeLink } from "@/components/home-link";
import { SkipLink } from "@/components/skip-link";

export function SiteHeader() {
  return (
    <>
      <SkipLink />
      <header className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-x-2 sm:flex-nowrap px-3 py-3 sm:px-6 sm:py-4">
        <div className="contents min-w-0 items-center sm:flex sm:gap-4">
          <HomeLink />
          <HeaderNav />
        </div>
        <LocaleSwitcher />
      </header>
    </>
  );
}
