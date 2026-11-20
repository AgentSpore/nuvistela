"use client";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";
import { GENRES, type Cover, type Genre } from "@/lib/adventure-api";

/** Three tones per genre, mirrored so the double-width layer can slide back and forth without a seam. */
const TONES: Record<Genre, [string, string, string]> = {
  fairy_tale: ["oklch(0.8 0.09 320)", "oklch(0.92 0.07 70)", "oklch(0.85 0.08 20)"],
  space: ["oklch(0.3 0.1 275)", "oklch(0.5 0.13 305)", "oklch(0.38 0.12 250)"],
  pirates: ["oklch(0.86 0.07 215)", "oklch(0.62 0.09 205)", "oklch(0.74 0.08 185)"],
  custom: ["oklch(0.93 0.05 90)", "oklch(0.84 0.06 150)", "oklch(0.88 0.06 40)"],
};
const sky = ([a, b, c]: [string, string, string]) =>
  `linear-gradient(100deg, ${a}, ${b}, ${c}, ${b}, ${a})`;
/** The gradient does not follow the theme, so neither does its text. */
const TEXT: Record<Genre, string> = {
  fairy_tale: "oklch(0.25 0.025 55)",
  space: "oklch(0.98 0.01 85)",
  pirates: "oklch(0.2 0.03 230)",
  custom: "oklch(0.25 0.025 55)",
};

/** `drawing` while the backend still paints the picture; `deferred` when it waits for tomorrow's budget; `loading` while a ready one downloads. */
type PlaceholderProps = {
  genre: Genre;
  drawing: boolean;
  deferred: boolean;
  loading: boolean;
};

/** The ink that reads on the genre's colours; the gradient does not follow the theme. */
export const genreInk = (genre: Genre): string => TEXT[genre];

/** The genre's drifting colours, decorative, filling its positioned parent. */
export function GenreSky({
  genre,
  drifting,
  testId,
  children,
}: {
  genre: Genre;
  drifting: boolean;
  testId?: string;
  children?: ReactNode;
}) {
  return (
    <div
      aria-hidden="true"
      data-testid={testId}
      className="absolute inset-0 overflow-hidden"
      style={{ color: TEXT[genre] }}
    >
      <div
        className={`absolute inset-y-0 left-0 w-[200%] ${drifting ? "cover-drift" : ""}`}
        style={{ backgroundImage: sky(TONES[genre]) }}
      />
      {children}
    </div>
  );
}

/** The genre's colours while the picture is drawn; the same box, so nothing moves. The title sits right below. */
function Placeholder({ genre, drawing, deferred, loading }: PlaceholderProps) {
  const t = useTranslations("adventure.world");
  return (
    <GenreSky
      genre={genre}
      drifting={drawing || loading}
      testId="world-cover-placeholder"
    >
      {drawing && (
        <p className="relative flex size-full items-center justify-center px-6 text-center font-display text-xl font-semibold sm:text-2xl">
          {t(deferred ? "coverTomorrow" : "coverDrawing")}
        </p>
      )}
    </GenreSky>
  );
}

/** A regenerated world has another title, so its first cover is not growth of the old one. */
const seenKey = (familyId: string, title: string) =>
  `nuvistela-cover-seen:${familyId}:${title}`;

function readSeenCover(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * True when the cover on screen differs from the one this family saw before: the world grew.
 * The first cover ever is not growth. The old url is fixed at mount, so the mark stays for the
 * whole visit; the new url is remembered at once, so a reload shows it as ordinary.
 */
function useGrownCover(key: string, url: string | null): boolean {
  const [before] = useState(() => readSeenCover(key) ?? url);
  useEffect(() => {
    if (url === null) return;
    try {
      localStorage.setItem(key, url);
    } catch {
      // Storage is off: the mark shows again next visit.
    }
  }, [key, url]);
  return url !== null && before !== null && url !== before;
}

type Props = {
  familyId: string;
  cover: Cover | null;
  growing: boolean;
  genre: string;
  title: string;
  compact: boolean;
  /** Overlaid at the bottom right of the picture, e.g. the 3D walk. */
  action?: ReactNode;
  /** Overlaid at the top right, e.g. the share entry. */
  topAction?: ReactNode;
};

/** One quiet line inside the picture box, top left clear of the action, so it moves nothing; a status the screen reader says once. */
function GrowthNote({ growing, grown }: { growing: boolean; grown: boolean }) {
  const t = useTranslations("adventure.world");
  const text = growing ? t("coverGrowing") : grown ? t("coverGrown") : null;
  return (
    <div role="status" className="absolute left-2 top-2">
      {text && (
        <p
          className={`rounded-full bg-honey-soft px-3 py-1 text-sm text-honey-ink ${growing ? "motion-safe:animate-pulse" : ""}`}
        >
          {text}
        </p>
      )}
    </div>
  );
}

/** At least 2:1 on a phone: the cover is the main picture, yet the first visit still shows the quest text above the fold. */
const coverAspect = (compact: boolean) =>
  compact ? "aspect-[2/1] md:aspect-[3/1]" : "aspect-[2/1] md:aspect-[5/2]";

/** A clean rectangle: the picture when ready and loaded, a placeholder while one is coming or lost; nothing when no picture exists. */
export function WorldCover(p: Props) {
  const { familyId, cover, growing, genre, title, compact, action, topAction } = p;
  const t = useTranslations("adventure.world");
  const [bad, setBad] = useState<string | null>(null);
  const [shown, setShown] = useState<string | null>(null);
  const url = cover?.status === "ready" ? cover.url : null;
  const usable = url !== null && url !== bad;
  const grown = useGrownCover(seenKey(familyId, title), usable ? url : null);
  if (cover === null) return null;
  return (
    <div
      className={`relative mb-4 overflow-hidden rounded-2xl bg-sunken ${coverAspect(compact)}`}
    >
      <Placeholder
        genre={GENRES.find((g) => g === genre) ?? "custom"}
        drawing={cover.status === "pending"}
        deferred={cover.deferred === true}
        loading={usable && shown !== url}
      />
      {usable && (
        // eslint-disable-next-line @next/next/no-img-element -- next/image rewrites src to an absolute URL even with unoptimized, and adds its own style; a plain img keeps the same-origin cookie path and the fixed DOM contract
        <img
          ref={(el) => {
            if (el?.complete && el.naturalWidth > 0) setShown(url);
          }}
          src={url}
          alt={t("coverAlt", { title })}
          width={1024}
          height={683}
          loading="eager"
          decoding="async"
          onLoad={() => setShown(url)}
          onError={() => setBad(url)}
          className={`absolute inset-0 size-full object-cover transition-opacity duration-500 motion-reduce:transition-none ${shown === url ? "opacity-100" : "opacity-0"}`}
        />
      )}
      <GrowthNote growing={growing} grown={grown} />
      <div className="absolute right-2 top-2">{topAction}</div>
      <div className="absolute bottom-2 right-2">{action}</div>
    </div>
  );
}
