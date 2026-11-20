import { HomeLink } from "@/components/home-link";
import { LocaleSwitcher } from "@/components/locale-switcher";

/** Header for pages shown to people without an account: logo and language only, no app navigation. */
export function CardHeader() {
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-2 px-3 py-3 sm:px-6 sm:py-4">
      <HomeLink />
      <LocaleSwitcher />
    </header>
  );
}
