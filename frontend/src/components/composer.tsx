"use client";
import { useTranslations } from "next-intl";
import { useLayoutEffect, useRef, type KeyboardEvent } from "react";
import { MAX_MESSAGE_CHARS } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { SendIcon } from "@/components/ui/icons";
import { focusRing } from "@/components/styles";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
};

const COUNTER_FROM = MAX_MESSAGE_CHARS * 0.8;

/** Message box: Enter sends, Shift+Enter adds a line, the counter appears near the limit. */
export function Composer({ value, onChange, onSend, busy }: Props) {
  const t = useTranslations("play");
  const box = useRef<HTMLTextAreaElement>(null);
  const length = Array.from(value).length;
  const over = length > MAX_MESSAGE_CHARS;
  const canSend = !busy && !over && value.trim().length > 0;

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [value]);

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey) return;
    if (e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
    e.preventDefault();
    if (canSend) onSend();
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSend();
      }}
      className="border-t border-line bg-card p-3 sm:p-4"
    >
      <div className="flex items-end gap-2.5">
        <textarea
          ref={box}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label={t("input")}
          aria-describedby="composer-hint"
          aria-invalid={over}
          placeholder={t("placeholder")}
          className={`min-h-12 min-w-0 flex-1 resize-none rounded-2xl border border-line-strong bg-paper px-4 py-3 text-base leading-snug aria-[invalid=true]:border-danger ${focusRing}`}
        />
        <Button
          type="submit"
          disabled={!canSend}
          aria-busy={busy}
          className="shrink-0 px-5"
        >
          <span className="max-[380px]:sr-only">{t("send")}</span>
          <SendIcon />
        </Button>
      </div>
      <div className="mt-1.5 flex min-h-5 items-center justify-between gap-3 px-1 text-xs text-muted">
        <p id="composer-hint" className="max-sm:sr-only">
          {t("hint")}
        </p>
        {length >= COUNTER_FROM && (
          <p
            role="status"
            aria-label={t("counterLabel", { count: length, max: MAX_MESSAGE_CHARS })}
            className={`ml-auto font-semibold tabular-nums ${over ? "text-danger" : ""}`}
          >
            {t("counter", { count: length, max: MAX_MESSAGE_CHARS })}
          </p>
        )}
      </div>
    </form>
  );
}
