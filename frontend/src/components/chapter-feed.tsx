"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { isPending, retryChapter, type Chapter } from "@/lib/adventure-api";
import { ApiError } from "@/lib/api";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type RetryNote = "limit" | "conflict" | "forbidden" | "failed";
const NOTE: Record<number, RetryNote> = {
  403: "forbidden",
  409: "conflict",
  429: "limit",
};
const noteOf = (e: unknown): RetryNote =>
  (e instanceof ApiError && NOTE[e.status]) || "failed";

/** A chapter on its way holds roughly a chapter's room, so the text arriving does not push what is below. */
const RESERVED = "min-h-80";
const CARD = "flex flex-col gap-2 rounded-3xl border border-line bg-card p-5 shadow-soft";

type CardProps = {
  chapter: Chapter;
  canRetry: boolean;
  onChanged: () => void;
  slow: boolean;
  fresh: boolean;
  onNote: (note: RetryNote | null, chapterId: string) => void;
};

type Held = { kind: RetryNote; chapterId: string; seen: string | null };

/** A retry note stays until its chapter is ready, gone, or changes status after the refresh (`seen`). */
function settle(held: Held | null, chapters: Chapter[]): Held | null {
  if (!held) return held;
  const status = chapters.find((c) => c.id === held.chapterId)?.status;
  if (!status || status === "ready") return null;
  if (held.seen === null) return { ...held, seen: status };
  return held.seen === status ? held : null;
}

const LINES = ["w-full", "w-11/12", "w-full", "w-2/3"];

function Waiting({ status, slow }: { status: "queued" | "writing"; slow: boolean }) {
  const t = useTranslations("adventure.chapter");
  return (
    <>
      <p className="font-semibold">{t(`${status}.title`)}</p>
      <p className="text-muted">{t(`${status}.text`)}</p>
      {LINES.map((w, i) => (
        <Skeleton key={i} className={`h-4 ${w}`} />
      ))}
      {slow && (
        <Alert tone="info" live={false}>
          {t("slow")}
        </Alert>
      )}
    </>
  );
}

function Delayed({ chapter, canRetry, onChanged, onNote }: CardProps) {
  const t = useTranslations("adventure");
  const [busy, setBusy] = useState(false);
  const status = chapter.status as "delayed_model" | "delayed_budget";

  async function retry() {
    setBusy(true);
    onNote(null, chapter.id);
    try {
      await retryChapter(chapter.id);
    } catch (e) {
      onNote(noteOf(e), chapter.id);
    }
    setBusy(false);
    onChanged();
  }

  return (
    <Alert
      tone="info"
      live={false}
      title={t(`chapter.${status}.title`)}
      action={
        canRetry && (
          <Button variant="ghost" onClick={retry} disabled={busy}>
            {t("retry")}
          </Button>
        )
      }
    >
      {t(`chapter.${status}.text`)}
    </Alert>
  );
}

function ChapterCard(props: CardProps) {
  const t = useTranslations("adventure.chapter");
  const { chapter } = props;
  return (
    <li
      id={`chapter-${chapter.id}`}
      data-fresh={props.fresh || undefined}
      className={`flex scroll-mt-4 flex-col gap-2 rounded-3xl border border-line p-5 shadow-soft transition-colors duration-700 motion-reduce:transition-none ${props.fresh ? "bg-honey-soft" : "bg-card"} ${isPending(chapter) ? RESERVED : ""}`}
    >
      <p className="text-sm font-semibold text-muted">
        {t("label", { seq: chapter.seq })}
      </p>
      {chapter.status === "ready" ? (
        <>
          <h3 className="font-display text-xl font-semibold">{chapter.title}</h3>
          <p className="whitespace-pre-line">{chapter.body}</p>
        </>
      ) : chapter.status === "queued" || chapter.status === "writing" ? (
        <Waiting status={chapter.status} slow={props.slow} />
      ) : (
        <Delayed {...props} />
      )}
    </li>
  );
}

/**
 * Before the first chapter: a plain hint. When a check-in is being sent it becomes the pending card
 * at a chapter's height at once (inside the grace after the tap), so the answer moves nothing below.
 */
function StoryEmpty({ reserve }: { reserve?: boolean }) {
  const t = useTranslations("adventure");
  if (!reserve) return <p className="text-muted">{t("storyEmpty")}</p>;
  return (
    <ol aria-hidden="true">
      <li className={`${CARD} ${RESERVED}`}>
        <p className="text-sm font-semibold text-muted">
          {t("chapter.label", { seq: 1 })}
        </p>
        <Waiting status="queued" slow={false} />
      </li>
    </ol>
  );
}

type Props = Omit<CardProps, "chapter" | "onNote" | "slow" | "fresh"> & {
  chapters: Chapter[];
  slowIds: string[];
  /** The chapter that just arrived after a check-in: softly highlighted. */
  freshId?: string | null;
  /** A check-in was just sent: keep a chapter's room instead of the «first chapter» hint. */
  reserve?: boolean;
};

/** "Our story": newest chapter first; one polite live line announces the newest status, none is faked. */
export function ChapterFeed({
  chapters,
  canRetry,
  onChanged,
  slowIds,
  freshId,
  reserve,
}: Props) {
  const t = useTranslations("adventure");
  const tc = useTranslations("common");
  const [held, setHeld] = useState<Held | null>(null);
  const [seen, setSeen] = useState(chapters);
  if (seen !== chapters) {
    setSeen(chapters);
    setHeld((h) => settle(h, chapters));
  }
  const newestFirst = [...chapters].sort((x, y) => y.seq - x.seq);
  const newest = newestFirst[0];
  const status =
    newest?.status === "ready"
      ? newest.title
      : newest && t(`chapter.${newest.status}.title`);
  const slowLabels = newestFirst
    .filter((c) => slowIds.includes(c.id))
    .map((c) =>
      tc("labelValue", {
        label: t("chapter.label", { seq: c.seq }),
        value: t("chapter.slow"),
      }),
    );
  const announce = [status, ...slowLabels].join(". ");
  return (
    <section aria-labelledby="story-title" className="flex flex-col gap-3">
      <p role="status" className="sr-only">
        {announce}
      </p>
      <h2 id="story-title" className="font-display text-xl font-semibold">
        {t("storyTitle")}
      </h2>
      {newestFirst.length === 0 && <StoryEmpty reserve={reserve} />}
      {held && <Alert>{t(`note.${held.kind}`)}</Alert>}
      <ol className="flex flex-col gap-3">
        {newestFirst.map((c) => (
          <ChapterCard
            key={c.id}
            chapter={c}
            canRetry={canRetry}
            onChanged={onChanged}
            slow={slowIds.includes(c.id)}
            fresh={c.id === freshId}
            onNote={(kind, chapterId) => setHeld(kind && { kind, chapterId, seen: null })}
          />
        ))}
      </ol>
    </section>
  );
}
