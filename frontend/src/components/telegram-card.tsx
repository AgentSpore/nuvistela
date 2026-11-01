"use client";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { issueTelegramCode, type LinkCode } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { cardCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CheckIcon, CopyIcon } from "@/components/ui/icons";

export const linkCommand = (code: string) => `/link@bot ${code}`;

function useExpired(expiresAt: Date): boolean {
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const left = Math.max(expiresAt.getTime() - Date.now(), 0);
    const timer = setTimeout(() => setExpired(true), left);
    return () => clearTimeout(timer);
  }, [expiresAt]);
  return expired;
}

function CodeView({ code, expiresAt }: { code: string; expiresAt: Date }) {
  const t = useTranslations("family.telegram");
  const format = useFormatter();
  const [copied, setCopied] = useState(false);
  const expired = useExpired(expiresAt);
  const command = linkCommand(code);
  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="rise flex flex-col gap-3">
      <p className="text-muted">{t("step")}</p>
      <div className="flex flex-col gap-2">
        <code className="min-w-0 flex-1 break-all rounded-xl border border-line-strong bg-sunken px-3.5 py-3 font-mono text-base">
          {command}
        </code>
        <Button variant="ghost" onClick={copy} className="shrink-0 self-start px-4">
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? t("copiedCommand") : t("copyCommand")}
        </Button>
      </div>
      <p className={`text-sm ${expired ? "font-semibold text-danger" : "text-muted"}`}>
        {expired
          ? t("expired")
          : t("expires", { time: format.dateTime(expiresAt, { timeStyle: "short" }) })}
      </p>
      <p className="text-sm text-muted">{t("privateHint")}</p>
    </div>
  );
}

/** Adults only: issues a one-time code that links a Telegram chat to the family. */
export function TelegramCard({ familyId }: { familyId: string }) {
  const t = useTranslations("family.telegram");
  const te = useTranslations("errors");
  const [code, setCode] = useState<{ code: string; expiresAt: Date } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inflight = useRef(false);
  async function issue() {
    if (inflight.current) return;
    inflight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const issued: LinkCode = await issueTelegramCode(familyId);
      setCode({ code: issued.code, expiresAt: new Date(issued.expires_at) });
    } catch (err) {
      setFailure(te(errorKey(err)));
    }
    inflight.current = false;
    setBusy(false);
  }
  return (
    <section aria-labelledby="tg-h" className={`${cardCls} flex flex-col gap-4`}>
      <div>
        <h2 id="tg-h" className="font-display text-xl font-semibold">
          {t("heading")}
        </h2>
        <p className="mt-1 text-muted">{t("intro")}</p>
      </div>
      {failure && <Alert>{failure}</Alert>}
      {code && <CodeView key={code.code} code={code.code} expiresAt={code.expiresAt} />}
      <Button
        variant={code ? "ghost" : "primary"}
        onClick={issue}
        disabled={busy}
        aria-busy={busy}
        className="self-start"
      >
        {code ? t("again") : t("get")}
      </Button>
    </section>
  );
}
