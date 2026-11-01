import { setRequestLocale } from "next-intl/server";
import { Landing } from "@/components/landing";
import { LandingView } from "@/components/landing-view";
import { SiteFooter } from "@/components/site-footer";

export default async function HomePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <>
      <LandingView locale={locale} />
      <Landing />
      <SiteFooter />
    </>
  );
}
