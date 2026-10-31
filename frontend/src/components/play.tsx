"use client";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { isAgentMissing, sendAgentMessage } from "@/lib/api";
import { useMe, useMembers } from "@/lib/use-me";
import { Gate } from "@/components/gate";
import { btnCls, inputCls } from "@/components/styles";

type Note = "soon" | "failed" | null;
type Message = { id: string; from: "me" | "agent"; text: string };

let nextId = 0;

const BUBBLE = {
  me: "max-w-[85%] self-end rounded-2xl bg-accent px-3 py-2 text-white",
  agent: "max-w-[85%] self-start rounded-2xl bg-honey/30 px-3 py-2",
};

function Members({ familyId }: { familyId: string }) {
  const t = useTranslations("play");
  const te = useTranslations("errors");
  const { members, failed } = useMembers(familyId);
  if (failed)
    return (
      <p role="alert" className="text-sm font-medium text-danger">
        {te("generic")}
      </p>
    );
  return (
    <ul aria-label={t("members")} className="flex flex-wrap gap-2">
      {members.map((x) => (
        <li
          key={x.id}
          className="rounded-full bg-accent/10 px-3 py-1 text-sm font-medium text-accent"
        >
          {x.display_name}
        </li>
      ))}
    </ul>
  );
}

export function Play() {
  const t = useTranslations("play");
  const me = useMe();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<Note>(null);
  const [busy, setBusy] = useState(false);
  const push = (from: Message["from"], text: string) =>
    setMessages((l) => [...l, { id: `m${nextId++}`, from, text }]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    push("me", text);
    setDraft("");
    setBusy(true);
    try {
      push("agent", (await sendAgentMessage(text)).reply);
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
            <Members familyId={m.family_id} />
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
              {messages.length === 0 && <li className="text-muted">{t("empty")}</li>}
              {messages.map((x) => (
                <li key={x.id} className={BUBBLE[x.from]}>
                  <span className="sr-only">
                    {t(x.from === "me" ? "you" : "agent")}:{" "}
                  </span>
                  {x.text}
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
