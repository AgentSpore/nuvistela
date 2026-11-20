import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonClass } from "@/components/ui/button";
import type { PublicShareData, ShareData } from "@/lib/share-api";
import { shareCtaPath } from "@/lib/share-cta";

function Cta({ locale }: { locale: string }) {
  const t = useTranslations("share");
  return (
    <a
      href={shareCtaPath(locale)}
      data-share-cta
      className={buttonClass("primary", "w-full sm:w-auto")}
    >
      {t("cta")}
    </a>
  );
}

type FrameProps = {
  as?: "main" | "div";
  coverUrl: string;
  coverAlt: string;
  title: ReactNode;
  locale: string;
  counts?: Counts;
};

type Counts = Pick<PublicShareData, "quests_done" | "chapters">;

/** "{n} deeds done · {m} chapters"; nothing while the family has done nothing yet. */
function CountsLine({ counts }: { counts?: Counts }) {
  const t = useTranslations("share");
  if (!counts || (counts.quests_done === 0 && counts.chapters === 0)) return null;
  return (
    <p data-share-counts className="font-display text-lg font-semibold text-ink">
      {t("counts", { quests: counts.quests_done, chapters: counts.chapters })}
    </p>
  );
}

/** The one card frame, shared by the real card and its placeholder so their boxes cannot drift. Inside the sender's sheet (`div`) the title slot holds two lines either way, so the arriving title does not move what is below it; the public page (`main`) is untouched. */
function ShareFrame({
  as: Root = "main",
  coverUrl,
  coverAlt,
  title,
  locale,
  counts,
}: FrameProps) {
  const t = useTranslations("share");
  return (
    <Root
      id={Root === "main" ? "main" : undefined}
      className="mx-auto w-full max-w-2xl px-4 pb-16 pt-4 sm:px-6 sm:pt-6"
    >
      <article className="overflow-hidden rounded-3xl border border-line bg-card shadow-soft">
        {/* eslint-disable-next-line @next/next/no-img-element -- public same-origin picture served with its own cache headers; works for bots and without scripts */}
        <img
          src={coverUrl}
          alt={coverAlt}
          width={1024}
          height={687}
          className="block aspect-[1024/687] h-auto w-full bg-sunken object-cover"
        />
        <div className="flex flex-col gap-4 p-5 sm:p-8">
          <div className={Root === "div" ? "min-h-[4.5rem] sm:min-h-20" : undefined}>
            {title}
          </div>
          <CountsLine counts={counts} />
          <p className="text-lg text-muted">{t("tagline")}</p>
          <Cta locale={locale} />
        </div>
      </article>
    </Root>
  );
}

/** The whole public card: picture, title (or genre words), one line, one way in. Plain HTML, no scripts. */
export function ShareCardView({
  card,
  locale,
  as,
}: {
  /** Counters are optional; both the public page and the sender's preview pass them. */
  card: ShareData & Partial<Counts>;
  locale: string;
  /** `div` where the card is shown inside another page (the sender's preview): one main per page. */
  as?: "main" | "div";
}) {
  const genre = useTranslations("adventure.genre");
  const world = useTranslations("adventure.world");
  const title = card.title ?? genre(card.genre);
  return (
    <ShareFrame
      as={as}
      coverUrl={card.cover_url}
      coverAlt={world("coverAlt", { title })}
      locale={locale}
      counts={
        card.quests_done === undefined || card.chapters === undefined
          ? undefined
          : { quests_done: card.quests_done, chapters: card.chapters }
      }
      title={
        <h1 className="text-balance break-words font-display text-3xl font-bold tracking-tight sm:text-4xl">
          {title}
        </h1>
      }
    />
  );
}

/** The card's frame before the sender's preview data arrives; the title is a bar. */
export function ShareCardSkeleton({
  coverUrl,
  locale,
}: {
  coverUrl: string;
  locale: string;
}) {
  return (
    <ShareFrame
      as="div"
      coverUrl={coverUrl}
      coverAlt=""
      locale={locale}
      title={<Skeleton className="h-9 w-2/3 sm:h-10" />}
    />
  );
}

export function ShareUnavailable({ locale }: { locale: string }) {
  const t = useTranslations("share");
  return (
    <main id="main" className="mx-auto w-full max-w-xl px-4 pb-16 pt-8 sm:px-6 sm:pt-16">
      <section className="flex flex-col gap-4 rounded-3xl border border-line bg-card p-6 shadow-soft sm:p-8">
        <h1 className="font-display text-3xl font-bold tracking-tight">
          {t("unavailableTitle")}
        </h1>
        <p className="text-lg text-muted">{t("unavailableText")}</p>
        <Cta locale={locale} />
      </section>
    </main>
  );
}
