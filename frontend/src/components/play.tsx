"use client";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { sendAgentMessage, type Member } from "@/lib/api";
import { agentNoteKey, type AgentNote } from "@/lib/errors";
import { useMe, useMembers } from "@/lib/use-me";
import { ChatMessage, type Message } from "@/components/chat-message";
import { Composer } from "@/components/composer";
import { Gate } from "@/components/gate";
import { Alert, type Tone } from "@/components/ui/alert";
import { Avatar } from "@/components/ui/avatar";
import { BeeMark } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";

let nextId = 0;

function MembersStrip({ familyId }: { familyId: string }) {
  const t = useTranslations("play");
  const { members, failed, loaded } = useMembers(familyId);
  if (failed) return null;
  if (!loaded) return <Skeleton className="h-9 w-64 max-w-full !rounded-full" />;
  return (
    <ul aria-label={t("members")} className="flex flex-wrap gap-2">
      {members.map((x) => (
        <li
          key={x.id}
          className="inline-flex items-center gap-2 rounded-full border border-line bg-card py-1 pr-3.5 pl-1 text-sm font-medium"
        >
          <Avatar id={x.id} name={x.display_name} size="sm" />
          {x.display_name}
        </li>
      ))}
    </ul>
  );
}

function EmptyChat() {
  const t = useTranslations("play");
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <span className="inline-flex size-16 items-center justify-center rounded-full bg-honey-soft [&_svg]:size-9">
        <BeeMark />
      </span>
      <p className="font-display text-xl font-semibold">{t("empty")}</p>
      <p className="max-w-[34ch] text-muted">{t("emptyHint")}</p>
    </div>
  );
}

function Typing() {
  const t = useTranslations("play");
  return (
    <div role="status" className="rise flex items-center gap-2.5 px-1 text-sm text-muted">
      <span className="inline-flex size-8 items-center justify-center rounded-full bg-honey-soft">
        <BeeMark />
      </span>
      <span className="inline-flex items-center gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{ animation: `dot 1.2s ${i * 0.15}s infinite` }}
            className="size-1.5 rounded-full bg-muted"
          />
        ))}
      </span>
      <span>{t("typing")}</span>
    </div>
  );
}

const NOTE_TONE: Partial<Record<AgentNote, Tone>> = {
  soon: "info",
  busy: "info",
  limit: "info",
  unavailable: "info",
};

function Chat({ me }: { me: Member }) {
  const t = useTranslations("play");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<AgentNote | null>(null);
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy, note]);

  async function send() {
    const text = draft.trim();
    const mine: Message = { id: `m${nextId++}`, from: "me", text };
    setMessages((l) => [...l, mine]);
    setDraft("");
    setNote(null);
    setBusy(true);
    try {
      const { reply } = await sendAgentMessage(text);
      setMessages((l) => [...l, { id: `m${nextId++}`, from: "agent", text: reply }]);
    } catch (err) {
      setMessages((l) => l.filter((x) => x.id !== mine.id));
      setDraft((d) => d || text);
      setNote(agentNoteKey(err));
    }
    setBusy(false);
  }

  return (
    <section
      aria-label={t("chat")}
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl border border-line bg-card shadow-soft"
    >
      <div
        ref={scroller}
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 sm:p-5"
      >
        {messages.length === 0 && !busy && <EmptyChat />}
        <div role="log" aria-live="polite">
          <ol className="flex flex-col gap-3.5">
            {messages.map((x) => (
              <ChatMessage
                key={x.id}
                message={x}
                senderId={me.id}
                senderName={x.from === "me" ? me.display_name : t("agent")}
              />
            ))}
          </ol>
        </div>
        {busy && <Typing />}
        {note && (
          <Alert tone={NOTE_TONE[note] ?? "danger"} title={t(`noteTitle.${note}`)}>
            {`${t(`note.${note}`)} ${t("restored")}`}
          </Alert>
        )}
      </div>
      <Composer value={draft} onChange={setDraft} onSend={send} busy={busy} />
    </section>
  );
}

export function Play() {
  const t = useTranslations("play");
  const me = useMe();
  return (
    <Gate state={me}>
      {(m) => (
        <div className="flex h-[calc(100dvh-4.75rem)] flex-col gap-3 sm:h-[calc(100dvh-5.5rem)]">
          <h1 className="sr-only">{t("title")}</h1>
          <MembersStrip familyId={m.family_id} />
          <Chat me={m} />
        </div>
      )}
    </Gate>
  );
}
