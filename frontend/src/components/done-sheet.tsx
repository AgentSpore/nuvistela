"use client";
import { useTranslations } from "next-intl";
import { flushSync } from "react-dom";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { clearDoneKey, doneKey, markQuestDone, type Quest } from "@/lib/adventure-api";
import { errorKey } from "@/lib/errors";
import { cardCls, inputCls } from "@/components/styles";
import { Celebration, prefersCalm } from "@/components/celebration";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

const MAX_NOTE = 280;

/** Told the moment a send starts and again if it fails, so the screen can make room before the answer. */
export const SendingContext = createContext<(sending: boolean) => void>(() => {});

type SheetProps = { quest: Quest; onClose: () => void; onDone: () => void };

type NoteProps = {
  note: string;
  onChange: (note: string) => void;
  boxRef: RefObject<HTMLTextAreaElement | null>;
};

function NoteField({ note, onChange, boxRef }: NoteProps) {
  const t = useTranslations("adventure");
  return (
    <>
      <label htmlFor="quest-note" className="font-semibold">
        {t("noteLabel")}
      </label>
      <textarea
        id="quest-note"
        ref={boxRef}
        rows={3}
        value={note}
        maxLength={MAX_NOTE}
        aria-describedby="quest-note-hint"
        onChange={(e) => onChange(e.target.value)}
        className={`${inputCls} resize-none`}
      />
      <p id="quest-note-hint" className="flex justify-between gap-3 text-sm text-muted">
        {t("noteHint")}
        <span className="shrink-0 whitespace-nowrap tabular-nums">
          {t("counter", { count: Array.from(note).length, max: MAX_NOTE })}
        </span>
      </p>
    </>
  );
}

type ActionsProps = { busy: boolean; onCancel: () => void; onSend: () => void };

function SheetActions({ busy, onCancel, onSend }: ActionsProps) {
  const t = useTranslations("adventure");
  return (
    <div className="grid grid-cols-2 gap-3">
      <Button variant="ghost" onClick={onCancel} disabled={busy}>
        {t("cancel")}
      </Button>
      <Button onClick={onSend} disabled={busy}>
        {busy ? t("sending") : t("send")}
      </Button>
    </div>
  );
}

/** Bottom sheet: optional note, one send. A failed send keeps the sheet and the same key. */
export function DoneSheet({ quest, onClose, onDone }: SheetProps) {
  const t = useTranslations("adventure");
  const te = useTranslations("errors");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const announce = useContext(SendingContext);
  // With a reaction to show, the sheet steps aside for the send: the one close event that causes is no dismissal.
  const swallowClose = useRef(false);
  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
    box.current?.focus();
  }, []);

  async function send() {
    setBusy(true);
    setError(null);
    announce(true);
    if (quest.reaction) {
      swallowClose.current = true;
      dialog.current?.close();
    }
    try {
      await markQuestDone(quest.id, note, doneKey(quest.id));
      clearDoneKey(quest.id);
      dialog.current?.close();
      onDone();
    } catch (e) {
      setError(te(errorKey(e)));
      setBusy(false);
      // The card must be visible again before the modal opens, or focus falls to <body>.
      flushSync(() => announce(false));
      if (!dialog.current?.open) dialog.current?.showModal();
      box.current?.focus();
    }
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby="sheet-title"
      onCancel={(e) => busy && e.preventDefault()}
      onClose={() => {
        if (swallowClose.current) swallowClose.current = false;
        else onClose();
      }}
      className="fixed inset-x-0 top-auto bottom-0 m-0 mx-auto max-h-[90dvh] w-full max-w-3xl flex-col gap-3 overflow-y-auto rounded-t-3xl border border-line bg-card p-5 text-ink shadow-soft backdrop:bg-ink/40 open:flex"
    >
      <h2 id="sheet-title" className="font-display text-xl font-semibold">
        {t("sheetTitle")}
      </h2>
      <NoteField note={note} onChange={setNote} boxRef={box} />
      {error && <Alert>{error}</Alert>}
      <SheetActions busy={busy} onCancel={() => dialog.current?.close()} onSend={send} />
    </dialog>
  );
}

function CheckIcon({ small, pop }: { small: boolean; pop: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className={`${small ? "size-8" : "size-12"} text-honey-deep ${pop ? "pop" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M7.5 12.5l3 3 6-6.5" />
    </svg>
  );
}

type RewardProps = {
  title: string;
  skill: string;
  height: number;
  reaction: string | null;
};

/** Takes the quest card's place at its height, so the chapter arriving below does not move the page. */
export function RewardCard({ title, skill, height, reaction }: RewardProps) {
  const t = useTranslations("adventure");
  const tc = useTranslations("common");
  const heading = useRef<HTMLHeadingElement>(null);
  const card = useRef<HTMLElement>(null);
  const [calm] = useState(prefersCalm);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    // A tall reaction can start below the fold: bring the whole card up, no animation if the reader asked for none.
    if (!reaction) return;
    card.current?.scrollIntoView?.({
      behavior: calm ? "auto" : "smooth",
      block: "nearest",
    });
  }, [reaction, calm]);
  return (
    <section
      ref={card}
      role="status"
      aria-labelledby="reward-title"
      style={{ minHeight: height }}
      className={`${cardCls} flex flex-col items-center justify-center gap-3 text-center`}
    >
      <Celebration calm={calm}>
        <CheckIcon small={reaction !== null} pop={!calm} />
      </Celebration>
      <h2
        id="reward-title"
        ref={heading}
        tabIndex={-1}
        aria-describedby={reaction ? "reward-reaction" : undefined}
        className={`font-display font-semibold outline-none ${reaction ? "text-lg text-muted" : "text-2xl"}`}
      >
        {t("reward.done", { title })}
      </h2>
      {reaction && (
        <p
          id="reward-reaction"
          className={`rise self-stretch rounded-lg font-display text-lg leading-relaxed text-start ${calm ? "" : "glow-line"}`}
        >
          <span className="sr-only">{t("reward.reaction")} </span>
          {reaction}
        </p>
      )}
      <p className="text-sm text-muted">
        {tc.rich("labelValueStyled", {
          label: t("skill"),
          value: skill,
          v: (chunks) => <span className="font-semibold text-ink">{chunks}</span>,
        })}
      </p>
      <p className="text-muted">{t("reward.writing")}</p>
    </section>
  );
}
