import { getLocale, setRequestLocale } from "next-intl/server";
import { ShareUnavailable } from "@/components/share-card";

export default async function ShareNotFound() {
  const locale = await getLocale();
  setRequestLocale(locale);
  return <ShareUnavailable locale={locale} />;
}
