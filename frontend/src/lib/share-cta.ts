import { routing } from "@/i18n/routing";

/** Landing root of a locale with the share attribution: never an invite, query or private fragment. */
export function shareCtaPath(locale: string): string {
  const supported =
    routing.locales.find((item) => item === locale) ?? routing.defaultLocale;
  return `${supported === routing.defaultLocale ? "/" : `/${supported}`}?source=share#demo`;
}
