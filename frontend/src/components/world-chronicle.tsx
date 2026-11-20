import { useTranslations } from "next-intl";
import type { ChronicleEntry } from "@/lib/adventure-api";

type Props = {
  chronicle: ChronicleEntry[];
  skills: string[];
  /** Chapters whose milestone is new to this family: tinted, never moved. */
  fresh: ReadonlySet<number>;
  /** Ref for the chronicle list: tells the hook when it is on screen. */
  observe: (list: HTMLOListElement | null) => void | (() => void);
};

/**
 * What changed in the world and what the family practised. Order alone tells the time: no
 * chapter numbers, counts or progress. Each part is absent when it has nothing to show.
 */
export function WorldChronicle({ chronicle, skills, fresh, observe }: Props) {
  const t = useTranslations("adventure.world");
  return (
    <>
      {chronicle.length > 0 && (
        <section aria-labelledby="chronicle-h">
          <h3 id="chronicle-h" className="font-semibold">
            {t("chronicle")}
          </h3>
          <ol
            ref={observe}
            aria-labelledby="chronicle-h"
            className="mt-2 flex flex-col gap-1"
          >
            {chronicle.map((e) => (
              <li
                key={e.chapter}
                className={`flex gap-2 rounded-xl border-l-4 px-3 py-2 ${
                  fresh.has(e.chapter)
                    ? "border-honey-deep bg-honey-soft"
                    : "border-transparent"
                }`}
              >
                {/* Colour alone must not say "new": the sparkle keeps its width on every line. */}
                <span
                  aria-hidden
                  className={`w-4 shrink-0 ${fresh.has(e.chapter) ? "" : "invisible"}`}
                >
                  ✦
                </span>
                {fresh.has(e.chapter) && (
                  <span className="sr-only">{t("chronicleNew")} </span>
                )}
                <span>{e.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
      {skills.length > 0 && (
        <section aria-labelledby="skills-h">
          <h3 id="skills-h" className="font-semibold">
            {t("learned")}
          </h3>
          <ul aria-labelledby="skills-h" className="mt-2 flex flex-wrap gap-2">
            {skills.map((s) => (
              <li
                key={s}
                className="rounded-full bg-honey-soft px-3 py-1 text-sm first-letter:uppercase"
              >
                {s}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
