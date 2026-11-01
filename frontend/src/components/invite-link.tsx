"use client";
import { useTranslations } from "next-intl";
import { useRef } from "react";
import { absoluteInvite, type Invite } from "@/lib/api";
import { CopyButton, CopyStatusText, useCopy } from "@/components/copy";
import { Avatar } from "@/components/ui/avatar";
import { inputCls } from "@/components/styles";

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
      <CopyStatusText status={status} labels={labels} />
    </li>
  );
}

export type Link = { id: string; name: string; url: string };

export const toLink = (i: Invite): Link => ({
  id: i.member.id,
  name: i.member.display_name,
  url: absoluteInvite(i.invite_url),
});
