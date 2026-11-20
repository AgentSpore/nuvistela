import { setRequestLocale } from "next-intl/server";
import { Adventure } from "@/components/adventure";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale);
  return (
    <main id="main" className="mx-auto w-full max-w-3xl px-3 sm:px-6">
      <Adventure />
    </main>
  );
}
