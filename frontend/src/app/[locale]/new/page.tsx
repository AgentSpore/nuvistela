import { setRequestLocale } from "next-intl/server";
import { NewFamily } from "@/components/new-family";
import { useTranslations } from "next-intl";
function Heading() {
  const t = useTranslations("new");
  return <h1 className="mb-4 text-2xl font-bold">{t("heading")}</h1>;
}
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <main id="main" className="mx-auto w-full max-w-2xl px-4 pb-8 sm:px-6">
      <Heading />
      <NewFamily />
    </main>
  );
}
