import { setRequestLocale } from "next-intl/server";
import { Join } from "@/components/join";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <main id="main" className="mx-auto w-full max-w-2xl px-4 pb-8 sm:px-6">
      <Join />
    </main>
  );
}
