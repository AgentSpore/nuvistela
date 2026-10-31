"use client";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { absoluteInvite, type Invite } from "@/lib/api";
import { btnGhostCls, inputCls } from "@/components/styles";

export function InviteLink({ name, url }: { name: string; url: string }) {
  const t = useTranslations("invite");
  const [copied, setCopied] = useState<boolean | null>(null);
  const input = useRef<HTMLInputElement>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
      input.current?.select();
    }
  }
  return (
    <li className="flex flex-col gap-2">
      <span className="font-medium">{name}</span>
      <div className="flex gap-2">
        <input
          ref={input}
          readOnly
          value={url}
          aria-label={t("linkFor", { name })}
          onFocus={(e) => e.currentTarget.select()}
          className={`${inputCls} min-w-0 flex-1 text-sm`}
        />
        <button type="button" onClick={copy} className={btnGhostCls}>
          {copied ? t("copied") : t("copy")}
        </button>
      </div>
      <span
        role="status"
        className={copied === false ? "text-sm font-medium text-danger" : "sr-only"}
      >
        {copied === null ? "" : copied ? t("copied") : t("copyFailed")}
      </span>
    </li>
  );
}

export type Link = { id: string; name: string; url: string };

export const toLink = (i: Invite): Link => ({
  id: i.member.id,
  name: i.member.display_name,
  url: absoluteInvite(i.invite_url),
});
