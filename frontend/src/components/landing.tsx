"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { LandingDemo } from "@/components/landing-demo";
import { recordPilotEvent, type PilotIntent } from "@/lib/pilot-events";
import Image from "next/image";
import { Link } from "@/i18n/navigation";
import { ExampleGallery } from "@/components/example-gallery";
import { exampleLoader } from "@/lib/example-loader";
import { buttonClass } from "@/components/ui/button";

const STEPS = [0, 1, 2] as const;

function Hero({ intent }: { intent: PilotIntent }) {
  const t = useTranslations("landing");
  const locale = useLocale();
  return (
    <section className="grid items-center gap-x-12 pt-6 pb-10 sm:py-20 lg:grid-cols-[1.15fr_0.85fr] lg:grid-rows-[auto_auto]">
      <div className="lg:col-start-1 lg:row-start-1">
        <p className="inline-flex items-center rounded-full border border-honey-deep/50 bg-honey-soft px-3.5 py-1 text-sm font-semibold">
          {t("eyebrow")}
        </p>
        <h1 className="mt-5 font-display text-4xl leading-[1.08] font-bold tracking-tight sm:text-5xl">
          {t("title")}
        </h1>
        <p className="mt-5 max-w-[40ch] text-lg leading-snug text-muted sm:text-2xl">
          {t("pitch")}
        </p>
      </div>
      <div className="lg:col-start-1 lg:row-start-2">
        <div className="mt-7 flex flex-wrap items-center gap-3 sm:mt-9">
          <Link
            href="/new"
            onClick={() => void recordPilotEvent("cta_click", locale, intent)}
            className={buttonClass("primary", "px-7 text-lg")}
          >
            {t("ctaTry")}
          </Link>
          <a href="#demo" className={buttonClass("ghost", "px-6 text-lg")}>
            {t("demoCta")}
          </a>
        </div>
        <p className="mt-5 max-w-[48ch] text-muted">{t("trust")}</p>
      </div>
      <Image
        src="/examples/hero-rainbow.webp"
        alt=""
        width={768}
        height={768}
        sizes="(min-width: 1024px) 40vw, (min-width: 640px) 448px, 100vw"
        loader={exampleLoader}
        preload
        fetchPriority="high"
        className="mt-6 aspect-[16/10] max-h-[40vh] w-full rounded-[2rem] border border-line object-cover shadow-soft sm:mt-10 sm:aspect-square sm:max-h-none sm:max-w-md lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mt-0 lg:max-w-none"
      />
    </section>
  );
}

function Steps() {
  const t = useTranslations("landing");
  return (
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
  );
}

export function Landing() {
  const [intent, setIntent] = useState<PilotIntent>(null);
  return (
    <main id="main" className="mx-auto w-full max-w-5xl px-5 pb-20 sm:px-8">
      <Hero intent={intent} />
      <LandingDemo intent={intent} onIntent={setIntent} />
      <Steps />
      <ExampleGallery />
    </main>
  );
}
