import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import { SITE_URL } from "@/lib/config";
import { Landing } from "@/components/landing";
import { LandingView } from "@/components/landing-view";
import { SiteFooter } from "@/components/site-footer";

const OG_LOCALE = { ru: "ru_RU", en: "en_US", es: "es_ES", "zh-CN": "zh_CN" } as const;
const OG_SIZE = { width: 1200, height: 630 } as const;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });
  const title = t("ogTitle");
  const description = t("ogDescription");
  const picture = locale === "ru" ? "og-ru.jpg" : "og-en.jpg";
  const images = [{ url: `${SITE_URL}/og/${picture}`, alt: t("ogImageAlt"), ...OG_SIZE }];
  const path = locale === routing.defaultLocale ? "" : locale;
  return {
    title,
    description,
    openGraph: {
      type: "website",
      url: `${SITE_URL}/${path}`,
      locale: OG_LOCALE[locale as keyof typeof OG_LOCALE],
      title,
      description,
      images,
    },
    twitter: { card: "summary_large_image", title, description, images },
  };
}

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
