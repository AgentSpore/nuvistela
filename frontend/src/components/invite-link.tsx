"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { btnGhostCls, inputCls } from "@/components/styles";

export function InviteLink({ name, url }: { name: string; url: string }) {
  const t = useTranslations("invite");
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <li className="flex flex-col gap-2">
      <span className="font-medium">{name}</span>
      <div className="flex gap-2">
        <input
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
      <span role="status" className="sr-only">
        {copied ? t("copied") : ""}
      </span>
    </li>
  );
}
