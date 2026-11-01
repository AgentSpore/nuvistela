import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { Avatar } from "@/components/ui/avatar";
import { buttonClass } from "@/components/ui/button";
import { BeeMark } from "@/components/ui/icons";

const STEPS = [0, 1, 2] as const;

function Peek() {
  const t = useTranslations("landing.peek");
  return (
    <div
      aria-hidden="true"
      className="rise flex flex-col gap-4 rounded-[2rem] border border-line bg-card p-5 shadow-soft [animation-delay:240ms] sm:p-7"
    >
      <p className="inline-flex w-fit items-center rounded-full bg-honey-soft px-3 py-1 text-sm font-semibold">
        {t("quest")}
      </p>
      <div className="flex items-end gap-2.5">
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-honey-soft">
          <BeeMark />
        </span>
        <div className="flex flex-col gap-0.5">
          <span className="px-1 text-xs font-semibold text-muted">{t("gmName")}</span>
          <p className="rounded-2xl rounded-bl-md border border-honey-deep/40 bg-honey-soft px-4 py-2.5 font-display leading-relaxed">
            {t("gm")}
          </p>
        </div>
      </div>
      <div className="flex flex-row-reverse items-end gap-2.5">
        <Avatar id="m-masha" name={t("kidName")} size="sm" />
        <div className="flex flex-col items-end gap-0.5">
          <span className="px-1 text-xs font-semibold text-muted">{t("kidName")}</span>
          <p className="rounded-2xl rounded-br-md bg-accent px-4 py-2.5 leading-relaxed text-paper">
            {t("kid")}
          </p>
        </div>
      </div>
    </div>
  );
}

export function Landing() {
  const t = useTranslations("landing");
  return (
    <main id="main" className="mx-auto w-full max-w-5xl px-5 pb-20 sm:px-8">
      <section className="grid items-center gap-12 py-10 sm:py-20 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
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
        </div>
        <Peek />
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
