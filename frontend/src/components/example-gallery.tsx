import Image from "next/image";
import { useTranslations } from "next-intl";
import { exampleLoader } from "@/lib/example-loader";

const SHOTS = [
  { file: "village", w: 768, h: 573 },
  { file: "islands", w: 429, h: 768 },
  { file: "beach", w: 768, h: 768 },
  { file: "ship", w: 768, h: 768 },
] as const;

export function ExampleGallery() {
  const t = useTranslations("landing.gallery");
  return (
    <section
      aria-labelledby="gal-h"
      className="mt-14 border-t border-line pt-10 sm:mt-20 sm:pt-14"
    >
      <h2 id="gal-h" className="font-display text-2xl font-semibold sm:text-3xl">
        {t("label")}
      </h2>
      <p className="mt-2 max-w-[56ch] text-muted">{t("note")}</p>
      <ul className="mt-7 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        {SHOTS.map((s, i) => (
          <li
            key={s.file}
            className="overflow-hidden rounded-2xl border border-line bg-sunken shadow-soft"
          >
            <Image
              src={`/examples/${s.file}.webp`}
              alt={t(`items.${i}.alt`)}
              width={s.w}
              height={s.h}
              sizes="(min-width: 640px) 25vw, 50vw"
              loader={exampleLoader}
              loading="lazy"
              className="aspect-square size-full object-cover"
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
