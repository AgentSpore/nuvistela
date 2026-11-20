"use client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import type { Genre } from "@/lib/adventure-api";
import { readWorldChoice, type WorldChoice } from "@/lib/world-choice";
import { genreInk, GenreSky } from "@/components/world-cover";
import { BeeMark } from "@/components/ui/icons";

/** How long each step is shown; the last one holds until the world is ready. */
export const WRITING_STEP_MS = 13_000;
const STEPS = ["places", "heroes", "quest"] as const;

const prefersCalm = () =>
  window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

/** The step to mark: moves on a timer, stays on the last; `null` under reduced motion (nothing moves). */
function useStep(calm: boolean): number | null {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (calm || step >= STEPS.length - 1) return;
    const timer = window.setTimeout(() => setStep(step + 1), WRITING_STEP_MS);
    return () => window.clearTimeout(timer);
  }, [calm, step]);
  return calm ? null : step;
}

function Quote({ choice }: { choice: WorldChoice | null }) {
  const t = useTranslations("adventure");
  if (!choice) return null;
  return (
    <figure className="flex max-w-[36ch] flex-col">
      <figcaption className="text-sm font-semibold opacity-80">
        {t("world.waitingYourWorld")}
      </figcaption>
      <blockquote className="line-clamp-2 font-display text-lg text-balance">
        {choice.kind === "text" ? choice.text : t(`genre.${choice.genre}`)}
      </blockquote>
    </figure>
  );
}

/** Done steps carry a check, the current one is bold, the rest are dimmed; all plain when nothing moves. */
function Steps({ step }: { step: number | null }) {
  const t = useTranslations("adventure.world");
  return (
    <ol className="flex flex-col gap-0.5 text-left">
      {STEPS.map((s, i) => {
        const done = step !== null && i < step;
        return (
          <li
            key={s}
            aria-current={step === i ? "step" : undefined}
            className={`flex gap-2 ${step === null || step === i ? "font-semibold" : "opacity-75"}`}
          >
            <span aria-hidden="true" className="w-4">
              {done ? "✓" : ""}
            </span>
            {t(`waitingSteps.${s}`)}
          </li>
        );
      })}
    </ol>
  );
}

const presetOf = (choice: WorldChoice | null): Genre =>
  choice?.kind === "genre" ? choice.genre : "custom";

/**
 * The wait for a world being written, sized by its content: the genre's colours behind the whole
 * card, what the player asked for and the story's next steps, no false progress. Without a
 * remembered preset (another adult chose, or a typed world) the neutral palette shows.
 */
export function WorldWriting({ familyId }: { familyId: string }) {
  const t = useTranslations("adventure.world");
  const [choice] = useState(() => readWorldChoice(familyId));
  const [calm] = useState(prefersCalm);
  const step = useStep(calm);
  const genre = presetOf(choice);
  return (
    <>
      <GenreSky genre={genre} drifting />
      <div
        className="relative flex flex-col items-center gap-2 pt-3"
        style={{ color: genreInk(genre) }}
      >
        <span className="inline-flex size-12 items-center justify-center rounded-full bg-honey-soft motion-safe:animate-bounce [&_svg]:size-7">
          <BeeMark />
        </span>
        <p className="font-display text-xl font-semibold">{t("waitingTitle")}</p>
        <Quote choice={choice} />
        <Steps step={step} />
        <p className="mt-1">{t("waitingText")}</p>
      </div>
    </>
  );
}
