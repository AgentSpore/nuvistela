"use client";
import { useTranslations } from "next-intl";
import { useRef, useState, type RefObject } from "react";
import type { Quest } from "@/lib/adventure-api";
import { useFullyVisible } from "@/lib/use-fully-visible";
import { DoneSheet } from "@/components/done-sheet";
import { QuestActionBar } from "@/components/quest-action-bar";
import { cardCls } from "@/components/styles";
import { Button } from "@/components/ui/button";

type Props = { quest: Quest; onDone: () => void };

export function QuestCard({ quest, onDone }: Props) {
  const t = useTranslations("adventure");
  const tc = useTranslations("common");
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const barButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const inView = useFullyVisible(trigger);
  const barred = inView === false;
  const close = () => {
    setOpen(false);
    const back = opener.current?.isConnected ? opener.current : trigger.current;
    back?.focus();
  };
  const openFrom = (button: RefObject<HTMLButtonElement | null>) => {
    opener.current = button.current;
    setOpen(true);
  };
  return (
    <section
      aria-labelledby="quest-label quest-title"
      className={`${cardCls} flex flex-col gap-3`}
    >
      <p id="quest-label" className="text-sm font-semibold text-muted">
        {t("questTitle")}
      </p>
      <h2 id="quest-title" className="font-display text-2xl font-semibold">
        {quest.title}
      </h2>
      <p>{quest.description}</p>
      <p className="text-sm text-muted">
        {tc.rich("labelValueStyled", {
          label: t("skill"),
          value: quest.skill,
          v: (chunks) => <span className="font-semibold text-ink">{chunks}</span>,
        })}
      </p>
      <Button ref={trigger} onClick={() => openFrom(trigger)}>
        {t("done")}
      </Button>
      {barred && (
        <QuestActionBar
          ref={barButton}
          fallback={trigger}
          onDone={() => openFrom(barButton)}
        />
      )}
      {open && <DoneSheet quest={quest} onClose={close} onDone={onDone} />}
    </section>
  );
}
