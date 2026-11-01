"use client";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { issueTelegramCode, type LinkCode } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { CopyButton, CopyStatusText, useCopy } from "@/components/copy";
import { cardCls, focusRing } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export const linkCommand = (bot: string, code: string) => `/link@${bot} ${code}`;
export const addToGroupUrl = (bot: string) => `https://t.me/${bot}?startgroup=1`;

function useExpired(expiresAt: Date): boolean {
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const left = Math.max(expiresAt.getTime() - Date.now(), 0);
    const timer = setTimeout(() => setExpired(true), left);
    return () => clearTimeout(timer);
  }, [expiresAt]);
  return expired;
}

type Issued = { code: string; expiresAt: Date; bot: string | null };

function Expiry({ expiresAt }: { expiresAt: Date }) {
  const t = useTranslations("family.telegram");
  const format = useFormatter();
  const expired = useExpired(expiresAt);
  // The provider's zone is the server's; the code is read on the user's clock.
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const time = format.dateTime(expiresAt, { timeStyle: "short", timeZone });
  return (
    <p className={`text-sm ${expired ? "font-semibold text-danger" : "text-muted"}`}>
      {expired ? t("expired") : t("expires", { time })}
    </p>
  );
}

function CodeView({
  code,
  expiresAt,
  bot,
}: {
  code: string;
  expiresAt: Date;
  bot: string;
}) {
  const t = useTranslations("family.telegram");
  const shown = useRef<HTMLElement>(null);
  const command = linkCommand(bot, code);
  const { status, copy } = useCopy(command, () => {
    const node = shown.current;
    if (node) window.getSelection()?.selectAllChildren(node);
  });
  const labels = {
    copy: t("copyCommand"),
    copied: t("copiedCommand"),
    failed: t("copyFailed"),
  };
  return (
    <div className="rise flex flex-col gap-3">
      <p className="text-muted">{t("step")}</p>
      <div className="flex flex-col gap-2">
        <code
          ref={shown}
          className="min-w-0 flex-1 break-all rounded-xl border border-line-strong bg-sunken px-3.5 py-3 font-mono text-base"
        >
          {command}
        </code>
        <div className="flex flex-wrap items-center gap-2">
          <CopyButton status={status} onCopy={copy} labels={labels} className="px-4" />
          <a
            href={addToGroupUrl(bot)}
            target="_blank"
            rel="noopener noreferrer"
            className={`rounded px-2 font-semibold text-accent underline underline-offset-4 decoration-accent/40 hover:decoration-accent ${focusRing}`}
          >
            {t("addToGroup")}
          </a>
        </div>
        <CopyStatusText status={status} labels={labels} />
      </div>
      <Expiry expiresAt={expiresAt} />
      <p className="text-sm text-muted">{t("privateHint")}</p>
    </div>
  );
}

/** Adults only: issues a one-time code that links a Telegram chat to the family. */
export function TelegramCard({ familyId }: { familyId: string }) {
  const t = useTranslations("family.telegram");
  const te = useTranslations("errors");
  const [code, setCode] = useState<Issued | null>(null);
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
      setCode({
        code: issued.code,
        expiresAt: new Date(issued.expires_at),
        bot: issued.bot_username,
      });
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
      {code?.bot === null && <Alert tone="info">{t("notConnected")}</Alert>}
      {code?.bot && (
        <CodeView
          key={code.code}
          code={code.code}
          expiresAt={code.expiresAt}
          bot={code.bot}
        />
      )}
      <Button
        variant={code?.bot ? "ghost" : "primary"}
        onClick={issue}
        disabled={busy}
        aria-busy={busy}
        className="self-start"
      >
        {code?.bot ? t("again") : t("get")}
      </Button>
    </section>
  );
}
