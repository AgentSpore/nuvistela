"use client";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  createShare,
  getShareState,
  revokeShare,
  type PublicShareData,
} from "@/lib/share-api";
import { ShareCardSkeleton, ShareCardView } from "@/components/share-card";
import { inputCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type Props = { familyId: string; coverUrl: string; onClose: () => void };
type Sent = "shared" | "cancelled" | "copied" | "failed";
type Fail = "unavailable" | "limit" | "generic";

const FAIL: Partial<Record<number, Fail>> = { 409: "unavailable", 429: "limit" };
const failKey = (e: unknown): Fail =>
  (e instanceof ApiError && e.kind === "http" && FAIL[e.status]) || "generic";

/** System share window, else clipboard. Cancelling the window is an outcome, not an error. */
async function send(url: string): Promise<Sent> {
  try {
    if (navigator.share) {
      await navigator.share({ url });
      return "shared";
    }
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch (error) {
    return error instanceof DOMException && error.name === "AbortError"
      ? "cancelled"
      : "failed";
  }
}

const linkOf = (locale: string, token: string) =>
  `${window.location.origin}/${locale}/w/${token}`;

type Card = Omit<PublicShareData, "cover_url">;

function useShareLink(familyId: string) {
  const locale = useLocale();
  const [card, setCard] = useState<Card | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [other, setOther] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);
  const [revoked, setRevoked] = useState(false);
  const [fail, setFail] = useState<Fail | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let ignore = false;
    getShareState(familyId).then(
      (state) => {
        if (ignore) return;
        setCard({
          title: state.title,
          genre: state.genre,
          quests_done: state.quests_done,
          chapters: state.chapters,
        });
        setOther(state.other_active);
        if (state.token) setUrl(linkOf(locale, state.token));
      },
      (e: unknown) => !ignore && setFail(failKey(e)),
    );
    return () => {
      ignore = true;
    };
  }, [familyId, locale]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setFail(null);
    try {
      await action();
    } catch (e) {
      setFail(failKey(e));
    } finally {
      setBusy(false);
    }
  }
  const create = () =>
    run(async () => {
      const { token } = await createShare(familyId);
      const link = linkOf(locale, token);
      setUrl(link);
      setRevoked(false);
      setSent(await send(link));
    });
  const revoke = () =>
    run(async () => {
      await revokeShare(familyId);
      setUrl(null);
      setOther(false);
      setSent(null);
      setRevoked(true);
    });
  return { card, url, other, sent, revoked, fail, busy, create, revoke };
}

function LinkBox({ url, sent }: { url: string; sent: Sent | null }) {
  const t = useTranslations("share.sheet");
  return (
    <div className="flex flex-col gap-2">
      {sent && (
        <p role="status" className="text-sm text-muted">
          {t(`status.${sent}`)}
        </p>
      )}
      <label htmlFor="share-link" className="font-semibold">
        {t("linkLabel")}
      </label>
      <input
        id="share-link"
        readOnly
        value={url}
        onFocus={(event) => event.target.select()}
        className={inputCls}
      />
    </div>
  );
}

function Revoke({ busy, onRevoke }: { busy: boolean; onRevoke: () => void }) {
  const t = useTranslations("share.sheet");
  const [asking, setAsking] = useState(false);
  if (!asking)
    return (
      <Button variant="ghost" onClick={() => setAsking(true)}>
        {t("revoke")}
      </Button>
    );
  return (
    <div role="group" aria-label={t("revoke")} className="flex flex-col gap-3">
      <p>{t("revokeAsk")}</p>
      <div className="grid grid-cols-2 gap-3">
        <Button variant="ghost" onClick={() => setAsking(false)} disabled={busy}>
          {t("revokeNo")}
        </Button>
        <Button onClick={onRevoke} disabled={busy}>
          {t("revokeYes")}
        </Button>
      </div>
    </div>
  );
}

/** Bottom sheet: the card exactly as others see it, the consent line, one create button; revoke asks inside the sheet. */
export function WorldShareSheet({ familyId, coverUrl, onClose }: Props) {
  const t = useTranslations("share.sheet");
  const locale = useLocale();
  const dialog = useRef<HTMLDialogElement>(null);
  const link = useShareLink(familyId);
  const shown = link.card && { ...link.card, cover_url: coverUrl };
  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      aria-labelledby="share-sheet-title"
      aria-busy={link.busy}
      onCancel={(e) => link.busy && e.preventDefault()}
      onClose={onClose}
      className="fixed inset-x-0 top-auto bottom-0 m-0 mx-auto max-h-[90dvh] w-full max-w-3xl flex-col gap-3 overflow-y-auto rounded-t-3xl border border-line bg-card p-5 text-ink shadow-soft backdrop:bg-ink/40 open:flex"
    >
      <h2 id="share-sheet-title" className="font-display text-xl font-semibold">
        {t("open")}
      </h2>
      <div inert className="[&>div]:p-0">
        {shown ? (
          <ShareCardView as="div" card={shown} locale={locale} />
        ) : (
          <ShareCardSkeleton coverUrl={coverUrl} locale={locale} />
        )}
      </div>
      {link.fail && <Alert>{t(`errors.${link.fail}`)}</Alert>}
      {link.revoked && <Alert tone="ok">{t("revoked")}</Alert>}
      {link.url ? (
        <LinkBox url={link.url} sent={link.sent} />
      ) : (
        <>
          <Button onClick={link.create} disabled={link.busy || link.card === null}>
            {t("create")}
          </Button>
          <p className="text-sm text-muted">{t("visibility")}</p>
        </>
      )}
      {(link.url || link.other) && <Revoke busy={link.busy} onRevoke={link.revoke} />}
      <Button
        variant="quiet"
        onClick={() => dialog.current?.close()}
        disabled={link.busy}
      >
        {t("close")}
      </Button>
    </dialog>
  );
}
