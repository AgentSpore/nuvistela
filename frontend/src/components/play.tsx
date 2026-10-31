"use client";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { isAgentMissing, sendAgentMessage } from "@/lib/api";
import { familyRoster } from "@/lib/roster";
import { useMe } from "@/lib/use-me";
import { Gate } from "@/components/gate";
import { btnCls, inputCls } from "@/components/styles";

type Note = "soon" | "failed" | null;

export function Play() {
  const t = useTranslations("play");
  const me = useMe();
  const [texts, setTexts] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<Note>(null);
  const [busy, setBusy] = useState(false);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setTexts((l) => [...l, text]);
    setDraft("");
    setBusy(true);
    try {
      await sendAgentMessage(text);
      setNote(null);
    } catch (err) {
      setNote(isAgentMissing(err) ? "soon" : "failed");
    }
    setBusy(false);
  }

  return (
    <Gate state={me}>
      {(m) => (
        <div className="flex min-h-[calc(100dvh-4rem)] flex-col gap-3">
          <header>
            <h1 className="sr-only">{t("title")}</h1>
            <ul aria-label={t("members")} className="flex flex-wrap gap-2">
              {familyRoster(m).map((x) => (
                <li
                  key={x.id}
                  className="rounded-full bg-accent/10 px-3 py-1 text-sm font-medium text-accent"
                >
                  {x.display_name}
                </li>
              ))}
            </ul>
          </header>
          <section
            aria-label={t("chat")}
            className="flex flex-1 flex-col gap-3 rounded-2xl border border-line bg-card p-3"
          >
            <ol
              role="log"
              aria-live="polite"
              className="flex flex-1 flex-col gap-2 overflow-y-auto"
            >
              {texts.length === 0 && <li className="text-muted">{t("empty")}</li>}
              {texts.map((x, i) => (
                <li
                  key={i}
                  className="max-w-[85%] self-end rounded-2xl bg-accent px-3 py-2 text-white"
                >
                  {x}
                </li>
              ))}
            </ol>
            {note && (
              <p
                role="status"
                className="rounded-lg bg-honey/30 px-3 py-2 text-sm font-medium"
              >
                {t(`note.${note}`)}
              </p>
            )}
            <form onSubmit={send} className="flex gap-2">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                aria-label={t("input")}
                placeholder={t("placeholder")}
                className={`${inputCls} min-w-0 flex-1`}
              />
              <button type="submit" disabled={busy} className={btnCls}>
                {t("send")}
              </button>
            </form>
          </section>
        </div>
      )}
    </Gate>
  );
}
