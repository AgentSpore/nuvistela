"use client";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { absoluteInvite, type Invite } from "@/lib/api";
import { CopyButton, CopyStatusText, useCopy } from "@/components/copy";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { inputCls } from "@/components/styles";

const ShareIcon = () => (
  <svg
    width={20}
    height={20}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M12 15V4M8 8l4-4 4 4M6 12v6.5A1.5 1.5 0 0 0 7.5 20h9a1.5 1.5 0 0 0 1.5-1.5V12" />
  </svg>
);

/** Invite links are shown once; the full note also says how to get a new one, `short` only the first part. */
export function InviteOnceNote({ short = false }: { short?: boolean }) {
  const t = useTranslations("invite");
  return <p className="text-sm text-muted">{t(short ? "onceShort" : "once")}</p>;
}

type Props = { id?: string; name: string; url: string };

export function InviteLink({ id, name, url }: Props) {
  const t = useTranslations("invite");
  const input = useRef<HTMLInputElement>(null);
  const { status, copy } = useCopy(url, () => input.current?.select());
  const labels = { copy: t("copy"), copied: t("copied"), failed: t("copyFailed") };
  return (
    <li className="rise flex flex-col gap-2">
      <span className="flex items-center gap-2.5 font-semibold">
        <Avatar id={id ?? name} name={name} size="sm" />
        {name}
      </span>
      <div className="flex gap-2">
        <input
          ref={input}
          readOnly
          value={url}
          aria-label={t("linkFor", { name })}
          onFocus={(e) => e.currentTarget.select()}
          className={`${inputCls} min-w-0 flex-1 truncate bg-sunken font-mono text-sm`}
        />
        <CopyButton
          status={status}
          onCopy={copy}
          labels={labels}
          className="shrink-0 px-4"
        />
      </div>
      <Button
        variant="ghost"
        onClick={() => void share(url, copy)}
        className="self-start px-4"
      >
        <ShareIcon />
        {t("share")}
      </Button>
      <CopyStatusText status={status} labels={labels} />
    </li>
  );
}

/** The system share sheet where there is one, otherwise the clipboard; a dismissed sheet is no error. */
async function share(url: string, copy: () => Promise<void>) {
  if (!navigator.share) return copy();
  try {
    await navigator.share({ url });
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) await copy();
  }
}

export type Link = { id: string; name: string; url: string };

export const toLink = (i: Invite): Link => ({
  id: i.member.id,
  name: i.member.display_name,
  url: absoluteInvite(i.invite_url),
});
