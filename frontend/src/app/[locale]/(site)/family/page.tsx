import { setRequestLocale } from "next-intl/server";
import { FamilyView } from "@/components/family-view";
import { SiteFooter } from "@/components/site-footer";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <>
      <main id="main" className="mx-auto min-h-dvh w-full max-w-5xl px-4 pb-16 sm:px-6">
        <FamilyView />
      </main>
      <SiteFooter />
    </>
  );
}
