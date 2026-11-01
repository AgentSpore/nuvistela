import { useTranslations } from "next-intl";
import Image from "next/image";
import { ExampleGallery } from "@/components/example-gallery";
import { WaitlistForm } from "@/components/waitlist-form";
import { cardCls } from "@/components/styles";
import { Link } from "@/i18n/navigation";
import { buttonClass } from "@/components/ui/button";

const STEPS = [0, 1, 2] as const;

export function Landing() {
  const t = useTranslations("landing");
  const w = useTranslations("waitlist");
  return (
    <main id="main" className="mx-auto w-full max-w-5xl px-5 pb-20 sm:px-8">
      <section className="grid items-center gap-12 py-10 sm:py-20 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <p className="rise inline-flex items-center rounded-full border border-honey-deep/50 bg-honey-soft px-3.5 py-1 text-sm font-semibold">
            {t("eyebrow")}
          </p>
          <h1 className="rise mt-5 font-display text-4xl leading-[1.08] font-bold tracking-tight [animation-delay:60ms] sm:text-6xl">
            {t("title")}
          </h1>
          <p className="rise mt-5 max-w-[40ch] text-lg leading-snug text-muted [animation-delay:120ms] sm:text-2xl">
            {t("pitch")}
          </p>
          <div className="rise mt-9 flex flex-wrap items-center gap-3 [animation-delay:180ms]">
            <a href="#waitlist" className={buttonClass("primary", "px-7 text-lg")}>
              {t("cta")}
            </a>
            <Link href="/new" className={buttonClass("ghost", "px-6 text-lg")}>
              {t("ctaTry")}
            </Link>
          </div>
          <p className="mt-5 max-w-[48ch] text-muted">{t("trust")}</p>
        </div>
        <Image
          src="/examples/hero-rainbow.webp"
          alt=""
          width={768}
          height={768}
          priority
          unoptimized
          className="rise aspect-square w-full max-w-md rounded-[2rem] border border-line object-cover shadow-soft [animation-delay:240ms] lg:max-w-none"
        />
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
      <ExampleGallery />
      <section
        id="waitlist"
        aria-labelledby="wl-h"
        className="mt-14 scroll-mt-4 grid gap-8 border-t border-line pt-10 sm:mt-20 sm:pt-14 lg:grid-cols-2"
      >
        <div>
          <h2 id="wl-h" className="font-display text-2xl font-semibold sm:text-3xl">
            {w("title")}
          </h2>
          <p className="mt-2 max-w-[40ch] text-muted">{w("lead")}</p>
        </div>
        <div className={cardCls}>
          <WaitlistForm />
        </div>
      </section>
    </main>
  );
}
