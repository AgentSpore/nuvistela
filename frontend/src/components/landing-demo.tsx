"use client";
import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import Image from "next/image";
import { Link } from "@/i18n/navigation";
import { exampleLoader } from "@/lib/example-loader";
import { PilotIntentChoice } from "@/components/pilot-intent";
import { Button, buttonClass } from "@/components/ui/button";
import { publicDemoUrl, recordPilotEvent, type PilotIntent } from "@/lib/pilot-events";

type Props = { intent: PilotIntent; onIntent: (intent: PilotIntent) => void };
type ShareStatus = "idle" | "closed" | "cancelled" | "copied" | "failed";

function ShareExample({ intent }: { intent: PilotIntent }) {
  const t = useTranslations("landing.demo");
  const locale = useLocale();
  const [status, setStatus] = useState<ShareStatus>("idle");
  const [busy, setBusy] = useState(false);
  async function share() {
    setBusy(true);
    void recordPilotEvent("share_click", locale, intent);
    try {
      const url = publicDemoUrl(locale);
      if (navigator.share) {
        await navigator.share({ url });
        setStatus("closed");
      } else {
        await navigator.clipboard.writeText(url);
        setStatus("copied");
      }
    } catch (error) {
      setStatus(
        error instanceof DOMException && error.name === "AbortError"
          ? "cancelled"
          : "failed",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-2">
      <Button variant="ghost" onClick={share} disabled={busy}>
        {t("share")}
      </Button>
      <p role="status" className="text-sm text-muted">
        {status !== "idle" && t(`shareStatus.${status}`)}
      </p>
      {status === "failed" && (
        <input
          aria-label={t("publicLink")}
          readOnly
          value={publicDemoUrl(locale)}
          onFocus={(event) => event.target.select()}
          className="w-full rounded-lg border border-line bg-card p-3 text-ink"
        />
      )}
    </div>
  );
}

function DemoChapter({
  intent,
  result,
}: {
  intent: PilotIntent;
  result: React.RefObject<HTMLHeadingElement | null>;
}) {
  const t = useTranslations("landing.demo");
  const locale = useLocale();
  return (
    <div className="mt-6 grid gap-6 sm:grid-cols-2">
      <Image
        src="/examples/hero-rainbow.webp"
        alt={t("imageAlt")}
        width={768}
        height={768}
        sizes="(min-width: 640px) 50vw, 100vw"
        loader={exampleLoader}
        className="aspect-square w-full rounded-2xl object-cover"
      />
      <div className="flex flex-col items-start gap-4">
        <h3 ref={result} tabIndex={-1} className="font-display text-2xl font-semibold">
          {t("chapterTitle")}
        </h3>
        <p>{t(intent === "solo" ? "soloChapter" : "familyChapter")}</p>
        <p className="text-sm text-muted">{t("sampleNote")}</p>
        <Link
          href="/new"
          onClick={() => void recordPilotEvent("cta_click", locale, intent)}
          className={buttonClass()}
        >
          {t("signup")}
        </Link>
        <ShareExample intent={intent} />
      </div>
    </div>
  );
}

export function LandingDemo({ intent, onIntent }: Props) {
  const t = useTranslations("landing.demo");
  const locale = useLocale();
  const [step, setStep] = useState<"choose" | "quest" | "chapter">("choose");
  const [shownIntent, setShownIntent] = useState(intent);
  if (shownIntent !== intent) {
    setShownIntent(intent);
    setStep("choose");
  }
  const result = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (step === "chapter") result.current?.focus();
  }, [step]);
  function advance() {
    if (!intent) return;
    void recordPilotEvent(
      step === "choose" ? "demo_start" : "demo_complete",
      locale,
      intent,
    );
    setStep(step === "choose" ? "quest" : "chapter");
  }
  return (
    <section
      id="demo"
      aria-labelledby="demo-title"
      className="scroll-mt-4 rounded-3xl border border-line bg-card p-6 shadow-soft sm:p-8"
    >
      <p className="text-sm font-semibold text-muted">{t("badge")}</p>
      <h2
        id="demo-title"
        className="mt-2 font-display text-2xl font-semibold sm:text-3xl"
      >
        {t("title")}
      </h2>
      <p className="my-4 max-w-[65ch] text-muted">{t("disclosure")}</p>
      <PilotIntentChoice intent={intent} onChange={onIntent} />
      {step !== "chapter" ? (
        <div className="mt-5 flex flex-col items-start gap-4">
          {step === "quest" && (
            <p className="text-lg">
              {t(intent === "solo" ? "soloQuest" : "familyQuest")}
            </p>
          )}
          <Button disabled={!intent} onClick={advance}>
            {t(step === "choose" ? "start" : "complete")}
          </Button>
        </div>
      ) : (
        <DemoChapter intent={intent} result={result} />
      )}
    </section>
  );
}
