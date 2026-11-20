import { setRequestLocale } from "next-intl/server";
import { Join } from "@/components/join";
import { SiteFooter } from "@/components/site-footer";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <>
      <main
        id="main"
        className="mx-auto min-h-dvh w-full max-w-xl px-4 pb-16 pt-6 sm:px-6 sm:pt-16"
      >
        <Join />
      </main>
      <SiteFooter />
    </>
  );
}
