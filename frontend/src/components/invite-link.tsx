"use client";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { absoluteInvite, type Invite } from "@/lib/api";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { CheckIcon, CopyIcon } from "@/components/ui/icons";
import { inputCls } from "@/components/styles";

type Props = { id?: string; name: string; url: string };

export function InviteLink({ id, name, url }: Props) {
  const t = useTranslations("invite");
  const [copied, setCopied] = useState<boolean | null>(null);
  const input = useRef<HTMLInputElement>(null);
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(null), 2400);
    } catch {
      setCopied(false);
      input.current?.select();
    }
  }
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
        <Button variant="ghost" onClick={copy} className="shrink-0 px-4">
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? t("copied") : t("copy")}
        </Button>
      </div>
      <span
        role="status"
        className={copied === false ? "text-sm font-semibold text-danger" : "sr-only"}
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
