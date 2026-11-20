import type { Metadata } from "next";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ShareCardView } from "@/components/share-card";
import { fetchShare, requestOrigin } from "@/lib/share-api";
import { ShareBeacon } from "./share-beacon";

type Props = { params: Promise<{ locale: string; token: string }> };

const NOINDEX = { index: false, follow: false } as const;
const COVER_SIZE = { width: 1024, height: 687 } as const;

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale, token } = await params;
  const card = await fetchShare(token);
  const t = await getTranslations({ locale, namespace: "share" });
  if (!card) return { title: t("unavailableTitle"), robots: NOINDEX };
  const genre = await getTranslations({ locale, namespace: "adventure.genre" });
  const title = t("ogTitle", { title: card.title ?? genre(card.genre) });
  const origin = requestOrigin(await headers());
  const images = origin
    ? [{ url: new URL(card.cover_url, origin).href, ...COVER_SIZE }]
    : undefined;
  const description = t("ogDescription");
  return {
    title,
    description,
    robots: NOINDEX,
    openGraph: { type: "website", title, description, images },
    twitter: { card: "summary_large_image", title, description, images },
  };
}

export default async function SharePage({ params }: Props) {
  const { locale, token } = await params;
  setRequestLocale(locale);
  const card = await fetchShare(token);
  if (!card) notFound();
  return (
    <>
      <ShareCardView card={card} locale={locale} />
      <ShareBeacon token={token} locale={locale} />
    </>
  );
}
