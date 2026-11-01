import { setRequestLocale } from "next-intl/server";
import { Play } from "@/components/play";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <main id="main" className="mx-auto w-full max-w-3xl px-3 pb-3 sm:px-6 sm:pb-6">
      <Play />
    </main>
  );
}
