"use client";
import { useTranslations } from "next-intl";
import type { Member } from "@/lib/api";
import { useMembers } from "@/lib/use-me";
import { useWorldPoll } from "@/lib/use-world-poll";
import { cardCls } from "@/components/styles";
import { BeeMark } from "@/components/ui/icons";

type Props = { me: Member; onPoll: () => void };

/**
 * A player who cannot choose the world waits here, told who is choosing it. The adventure is
 * re-read every few seconds (not while the tab is hidden), so the quest replaces this by itself.
 */
export function WorldWait({ me, onPoll }: Props) {
  const t = useTranslations("adventure");
  const { members, loaded, failed } = useMembers(me.family_id);
  const owner = members.find((x) => x.is_owner && x.id !== me.id);
  useWorldPoll(onPoll);
  return (
    <section
      role="status"
      className={`${cardCls} rise flex flex-col items-center gap-4 text-center`}
    >
      <span className="inline-flex size-20 items-center justify-center rounded-full bg-honey-soft motion-safe:animate-bounce [&_svg]:size-11">
        <BeeMark />
      </span>
      {/* Reserved height: the headline is written once, when the owner's name is known. */}
      <p className="min-h-14 font-display text-xl font-semibold text-balance">
        {(loaded || failed) &&
          (owner ? t("waitWorld", { name: owner.display_name }) : t("waitWorldAnyone"))}
      </p>
      <p className="max-w-[36ch] text-muted">{t("waitWorldHint")}</p>
    </section>
  );
}
