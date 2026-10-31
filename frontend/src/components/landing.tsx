import { useTranslations } from "next-intl";

export function Landing() {
  const t = useTranslations("landing");
  return (
    <main
      id="main"
      className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-6 py-12"
    >
      <h1 className="text-4xl font-bold tracking-tight text-accent sm:text-6xl">
        {t("title")}
      </h1>
      <p className="mt-4 text-lg text-ink sm:text-2xl">{t("pitch")}</p>
    </main>
  );
}
