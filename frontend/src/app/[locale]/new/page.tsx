import { setRequestLocale } from "next-intl/server";
import { NewFamily } from "@/components/new-family";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <main id="main" className="mx-auto w-full max-w-2xl px-4 pb-16 pt-2 sm:px-6 sm:pt-8">
      <NewFamily />
    </main>
  );
}
