"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import type { Cover } from "@/lib/adventure-api";
import { useMe } from "@/lib/use-me";
import { WorldShareSheet } from "@/components/world-share-sheet";
import { Button } from "@/components/ui/button";

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
    <path d="M12 3v12M8 7l4-4 4 4M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7" />
  </svg>
);

type Props = { familyId: string; cover: Cover | null };

/** The share entry, an icon button for the cover's top right corner: only an adult, only once the cover is a ready picture. Opens the preview and consent sheet. */
export function WorldShare({ familyId, cover }: Props) {
  const t = useTranslations("share.sheet");
  const me = useMe();
  const [open, setOpen] = useState(false);
  const url = cover?.status === "ready" ? cover.url : null;
  if (url === null || me.status !== "ready" || me.me.role !== "adult") return null;
  return (
    <>
      <Button
        variant="ghost"
        className="min-w-12 !px-3 shadow-soft"
        aria-label={t("open")}
        onClick={() => setOpen(true)}
      >
        <ShareIcon />
      </Button>
      {open && (
        <WorldShareSheet
          familyId={familyId}
          coverUrl={url}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
