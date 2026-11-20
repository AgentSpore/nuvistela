"use client";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAdventure,
  getWorld,
  WORLD_READ_TIMEOUT_MS,
  startAdventure,
  type Adventure,
  type Genre,
} from "@/lib/adventure-api";
import { ApiError } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { clearWorldChoice, saveWorldChoice } from "@/lib/world-choice";
import { useWorldPoll } from "@/lib/use-world-poll";
import { cardCls, focusRing, inputCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type Props = {
  familyId: string;
  onStarted: (outcome: Outcome) => void;
  /** Asks again whether another adult has chosen the world meanwhile. */
  onPoll: () => void | Promise<unknown>;
  /** Reports whether the player has started typing a description, so the screen can say it was dropped. */
  onTyping?: (typing: boolean) => void;
};

export const MAX_WORLD = 300;
const NEAR_LIMIT = 30;
const focusField = () => document.getElementById("a-custom")?.focus();
const PRESETS = ["fairy_tale", "space", "pirates"] as const satisfies readonly Genre[];
const EXAMPLES = ["one", "two", "three", "four"] as const;

type Choice = { genre: (typeof PRESETS)[number] | null; text: string };

type OwnWorldProps = {
  text: string;
  tooLong: boolean;
  onText: (v: string) => void;
};

function OwnWorld({ text, tooLong, onText }: OwnWorldProps) {
  const t = useTranslations("adventure");
  const tp = useTranslations("play");
  const describedBy = ["a-custom-hint", "a-custom-count", tooLong && "a-custom-err"]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="a-custom" className="text-[0.95rem] font-semibold">
        {t("customLabel")}
      </label>
      <textarea
        id="a-custom"
        rows={4}
        value={text}
        maxLength={MAX_WORLD}
        onChange={(e) => onText(e.target.value)}
        aria-invalid={tooLong}
        aria-describedby={describedBy}
        className={`${inputCls} resize-y`}
      />
      <div className="flex justify-between gap-3 text-sm text-muted">
        <p id="a-custom-hint">{t("customHint")}</p>
        <p
          id="a-custom-count"
          aria-live={text.length > MAX_WORLD - NEAR_LIMIT ? "polite" : "off"}
          className="shrink-0 tabular-nums"
        >
          <span className="sr-only">
            {tp("counterLabel", { count: text.length, max: MAX_WORLD })}
          </span>
          <span aria-hidden="true">
            {t("counter", { count: text.length, max: MAX_WORLD })}
          </span>
        </p>
      </div>
      {tooLong && (
        <p
          id="a-custom-err"
          role="alert"
          className="rise text-sm font-semibold text-danger"
        >
          {t("customTooLong", { max: MAX_WORLD })}
        </p>
      )}
    </div>
  );
}

function Examples({ onPick }: { onPick: (v: string) => void }) {
  const t = useTranslations("adventure");
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-semibold text-muted">{t("examplesLabel")}</p>
      <ul className="flex flex-col gap-2">
        {EXAMPLES.map((k) => (
          <li key={k}>
            <button
              type="button"
              onClick={() => onPick(t(`examples.${k}`))}
              className={`min-h-12 w-full rounded-2xl border border-line bg-sunken px-3.5 py-2.5 text-left text-[0.95rem] hover:border-ink/40 ${focusRing}`}
            >
              {t(`examples.${k}`)}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Presets({
  genre,
  onPick,
}: {
  genre: Choice["genre"];
  onPick: (g: Genre) => void;
}) {
  const t = useTranslations("adventure");
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-3 text-sm font-semibold text-muted">
        {t("presetsLabel")}
      </legend>
      <div className="grid grid-cols-3 gap-2">
        {PRESETS.map((g) => (
          <label
            key={g}
            className="flex min-h-12 cursor-pointer items-center justify-center rounded-2xl border border-line-strong bg-card px-2 text-center font-semibold has-checked:border-honey-deep has-checked:bg-honey-soft has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent"
          >
            <input
              type="radio"
              name="genre"
              value={g}
              checked={genre === g}
              onChange={() => onPick(g)}
              className="sr-only"
            />
            {t(`genre.${g}`)}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Nothing has been chosen yet: no world, no quest, no chapter. */
export const isUnchosen = (a: Adventure): boolean =>
  a.world === null && a.quest === null && a.chapters.length === 0;

/** The genre of the world stored for the family, or null when it cannot be read. */
async function storedGenre(familyId: string): Promise<string | null> {
  try {
    return (await getWorld(familyId)).genre;
  } catch {
    return null;
  }
}

export type Outcome = "mine" | "taken";

/**
 * Starts the world unless one is already there (read fresh right before the POST; an unreadable
 * state proceeds to the POST). Whether the stored world is this player's is judged by its genre
 * against the pick: a retry after a lost response matches and is ours. A custom text against
 * another custom text, or the same preset chosen by two adults between the pre-check and the POST,
 * cannot be told apart and counts as ours; so does an unreadable stored genre after our own POST.
 * The quote for the wait screen is kept only for a world judged ours.
 */
async function begin(familyId: string, choice: Choice): Promise<Outcome> {
  clearWorldChoice(familyId);
  const fresh = await getAdventure(familyId, WORLD_READ_TIMEOUT_MS).catch(() => null);
  const exists = fresh !== null && !isUnchosen(fresh);
  const own = choice.text.trim();
  if (!exists)
    await (choice.genre
      ? startAdventure(familyId, choice.genre)
      : startAdventure(familyId, "custom", own));
  const stored = await storedGenre(familyId);
  const pick = choice.genre ?? "custom";
  if (exists ? stored !== pick : stored !== null && stored !== pick) return "taken";
  saveWorldChoice(
    familyId,
    choice.genre ? { kind: "genre", genre: choice.genre } : { kind: "text", text: own },
  );
  return "mine";
}

export function AdventureStart({ familyId, onStarted, onPoll, onTyping }: Props) {
  const t = useTranslations("adventure");
  const te = useTranslations("errors");
  const [choice, setChoice] = useState<Choice>({ genre: null, text: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tooLong, setTooLong] = useState(false);
  const ready = choice.genre !== null || choice.text.trim().length > 0;

  const starting = useRef(false);
  // A reload mid-start would swap this form for the wait card before the quote is saved.
  useWorldPoll(useCallback(() => (starting.current ? undefined : onPoll()), [onPoll]));
  useEffect(() => {
    if (tooLong) focusField();
  }, [tooLong]);

  const pickExample = (text: string) => {
    setText(text);
    focusField();
  };
  const setText = (text: string) => {
    onTyping?.(text.trim().length > 0);
    setTooLong(false);
    setChoice({ genre: null, text });
  };
  const pickGenre = (genre: Genre) => {
    if (genre === "custom") return;
    onTyping?.(false);
    setTooLong(false);
    setChoice({ genre, text: "" });
  };

  async function start() {
    setBusy(true);
    setError(null);
    setTooLong(false);
    starting.current = true;
    try {
      onStarted(await begin(familyId, choice));
    } catch (e) {
      if (e instanceof ApiError && e.kind === "http" && e.status === 422)
        setTooLong(true);
      else setError(te(errorKey(e)));
    }
    starting.current = false;
    setBusy(false);
  }

  return (
    <section className={`${cardCls} flex flex-col gap-5`}>
      <div>
        <h2 className="font-display text-xl font-semibold">{t("startTitle")}</h2>
        <p className="mt-1 text-muted">{t("startHint")}</p>
      </div>
      <OwnWorld text={choice.text} tooLong={tooLong} onText={setText} />
      <Examples onPick={pickExample} />
      <Presets genre={choice.genre} onPick={pickGenre} />
      {error && <Alert>{error}</Alert>}
      <Button onClick={start} disabled={busy || !ready} className={focusRing}>
        {busy ? t("starting") : t("start")}
      </Button>
    </section>
  );
}
