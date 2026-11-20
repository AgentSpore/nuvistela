import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Policy, policySectionsSchema } from "@/components/policy";
import { SiteFooter } from "@/components/site-footer";

type Props = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "privacy" });
  return { title: t("title") };
}

export default async function Page({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "privacy" });
  const sections = policySectionsSchema.parse(t.raw("sections"));
  return (
    <>
      <main
        id="main"
        className="mx-auto w-full max-w-3xl px-4 pb-16 pt-2 sm:px-6 sm:pt-8"
      >
        <h1 className="font-display text-2xl font-bold break-words sm:text-4xl">
          {t("title")}
        </h1>
        <p className="mt-2 text-muted">
          {t("effective")} {t("versionLabel")}: {t("version")}
        </p>
        <Policy sections={sections} />
      </main>
      <SiteFooter />
    </>
  );
}
