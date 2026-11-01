import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { buttonClass } from "@/components/ui/button";

const STEPS = [0, 1, 2] as const;

export function Landing() {
  const t = useTranslations("landing");
  return (
    <main id="main" className="mx-auto w-full max-w-5xl px-5 pb-20 sm:px-8">
      <section className="py-10 sm:py-20">
        <p className="rise inline-flex items-center rounded-full border border-honey-deep/50 bg-honey-soft px-3.5 py-1 text-sm font-semibold">
          {t("eyebrow")}
        </p>
        <h1 className="rise mt-5 font-display text-[3.4rem] leading-[1.02] font-bold tracking-tight [animation-delay:60ms] sm:text-8xl">
          {t("title")}
        </h1>
        <p className="rise mt-5 max-w-[34ch] text-xl leading-snug text-muted [animation-delay:120ms] sm:text-3xl">
          {t("pitch")}
        </p>
        <div className="rise mt-9 flex flex-wrap items-center gap-3 [animation-delay:180ms]">
          <Link href="/new" className={buttonClass("primary", "px-7 text-lg")}>
            {t("cta")}
          </Link>
          <Link href="/play" className={buttonClass("ghost", "px-6 text-lg")}>
            {t("ctaPlay")}
          </Link>
        </div>
        <p className="mt-5 max-w-[48ch] text-muted">{t("trust")}</p>
      </section>
      <section aria-labelledby="how-h" className="border-t border-line pt-10 sm:pt-14">
        <h2 id="how-h" className="font-display text-2xl font-semibold sm:text-3xl">
          {t("stepsLabel")}
        </h2>
        <ol className="mt-8 grid gap-9 sm:grid-cols-3 sm:gap-8">
          {STEPS.map((i) => (
            <li key={i} className="flex gap-4 sm:flex-col sm:gap-3">
              <span
                aria-hidden="true"
                className="font-display text-5xl leading-none font-bold text-honey-deep sm:text-6xl"
              >
                {i + 1}
              </span>
              <div>
                <h3 className="text-xl font-semibold">{t(`steps.${i}.t`)}</h3>
                <p className="mt-1.5 max-w-[34ch] text-muted">{t(`steps.${i}.d`)}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
