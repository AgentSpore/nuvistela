"use client";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAdventure,
  isPending,
  type Adventure as AdventureData,
  type Chapter,
  type Quest,
} from "@/lib/adventure-api";
import type { Member } from "@/lib/api";
import { useAdventure } from "@/lib/use-adventure";
import { useMe } from "@/lib/use-me";
import { AdventureStart, isUnchosen } from "@/components/adventure-start";
import { ChapterFeed } from "@/components/chapter-feed";
import { RewardCard, SendingContext } from "@/components/done-sheet";
import { Gate } from "@/components/gate";
import { PushOptIn } from "@/components/push-optin";
import { QuestCard } from "@/components/quest-card";
import { WorldPanel } from "@/components/world-panel";
import { WorldWait } from "@/components/world-wait";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type ViewProps = {
  /** The player was typing a world when another adult's choice replaced the form. */
  taken: boolean;
  me: Member;
  data: AdventureData;
  paused: boolean;
  slow: boolean;
  slowChapterIds: string[];
  reload: () => void;
};

const FRESH_MS = 4000;

type Reward = {
  title: string;
  skill: string;
  height: number;
  reaction: string | null;
  afterSeq: number;
};

/**
 * After a check-in the quest card gives way to a reward card until the new chapter has settled;
 * a ready chapter is then scrolled to (no smooth scroll under reduced motion) and softly highlighted.
 */
function useReward(chapters: Chapter[]) {
  const [reward, setReward] = useState<Reward | null>(null);
  const [freshId, setFreshId] = useState<string | null>(null);
  const arrived = reward ? chapters.find((c) => c.seq > reward.afterSeq) : undefined;
  if (reward && arrived && !isPending(arrived)) {
    setReward(null);
    setFreshId(arrived.status === "ready" ? arrived.id : null);
  }
  useEffect(() => {
    if (!freshId) return;
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    document
      .getElementById(`chapter-${freshId}`)
      ?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
    const timer = window.setTimeout(() => setFreshId(null), FRESH_MS);
    return () => window.clearTimeout(timer);
  }, [freshId]);
  const begin = (q: Quest, height: number) =>
    setReward((r) => ({
      title: q.title,
      skill: q.skill,
      height: r?.height ?? height,
      reaction: q.reaction ?? null,
      afterSeq: r?.afterSeq ?? Math.max(0, ...chapters.map((c) => c.seq)),
    }));
  return { reward, freshId, begin, cancel: () => setReward(null) };
}

type OpenQuestProps = {
  quest: Quest;
  hidden: boolean;
  onSending: (sending: boolean, height: number) => void;
  onSent: (quest: Quest, height: number) => void;
};

/**
 * The quest card, measured so the reward card can take its place at the same height. While the
 * reward stands in for it the card stays mounted, hidden: its sheet still owns a failed send.
 */
function OpenQuest({ quest, hidden, onSending, onSent }: OpenQuestProps) {
  const slot = useRef<HTMLDivElement>(null);
  return (
    <div ref={slot} hidden={hidden}>
      <SendingContext
        value={(sending) => onSending(sending, slot.current?.offsetHeight ?? 0)}
      >
        <QuestCard
          key={quest.id}
          quest={quest}
          onDone={() => onSent(quest, slot.current?.offsetHeight ?? 0)}
        />
      </SendingContext>
    </div>
  );
}

/** Open until the first chapter has arrived; a returning player's choice is left alone. */
const isFirstVisit = (chapters: Chapter[], reward: Reward | null) =>
  chapters.length === 0 || reward?.afterSeq === 0;

/** Once the reward and the fresh-chapter highlight have settled, for an adult with a chapter to show. */
const canOfferPush = (
  me: Member,
  chapters: Chapter[],
  reward: Reward | null,
  freshId: string | null,
) =>
  me.role === "adult" &&
  reward === null &&
  freshId === null &&
  chapters.some((c) => c.status === "ready");

function Notices({ paused, taken }: { paused: boolean; taken: boolean }) {
  const t = useTranslations("adventure");
  return (
    <>
      {paused && <Alert tone="info">{t("paused")}</Alert>}
      {taken && <Alert tone="info">{t("worldTaken")}</Alert>}
    </>
  );
}

function Story({ taken, me, data, paused, slow, slowChapterIds, reload }: ViewProps) {
  const t = useTranslations("adventure");
  const { reward, freshId, begin, cancel } = useReward(data.chapters);
  const [sending, setSending] = useState(false);
  const after = (
    <>
      {reward && <RewardCard {...reward} />}
      {data.quest ? (
        <OpenQuest
          quest={data.quest}
          hidden={reward !== null}
          onSending={(on, height) => {
            setSending(on);
            if (!on) cancel();
            else if (data.quest?.reaction) begin(data.quest, height);
          }}
          onSent={(q, height) => {
            begin(q, height);
            setSending(false);
            reload();
          }}
        />
      ) : (
        !reward &&
        data.chapters.length > 0 && <p className="text-muted">{t("waitingQuest")}</p>
      )}
      {(data.quest || data.chapters.length > 0) && (
        <ChapterFeed
          chapters={data.chapters}
          canRetry={me.role === "adult"}
          slowIds={slowChapterIds}
          freshId={freshId}
          reserve={sending || reward !== null}
          onChanged={reload}
        />
      )}
      <PushOptIn when={canOfferPush(me, data.chapters, reward, freshId)} />
    </>
  );
  return (
    <>
      <Notices paused={paused} taken={taken} />
      {data.world ? (
        <WorldPanel
          familyId={me.family_id}
          status={data.world.status}
          memberId={me.id}
          firstVisit={isFirstVisit(data.chapters, reward)}
          slow={slow}
          chronicle={data.chronicle}
          skills={data.skills}
        >
          {after}
        </WorldPanel>
      ) : (
        after
      )}
    </>
  );
}

function Screen({ me }: { me: Member }) {
  const t = useTranslations("adventure");
  const [typed, setTyped] = useState(false);
  const [taken, setTaken] = useState(false);
  const { state, paused, slow, slowChapterIds, reload } = useAdventure(me.family_id);
  const poll = useCallback(async () => {
    if (!isUnchosen(await getAdventure(me.family_id))) reload();
  }, [me.family_id, reload]);
  if (state.status === "loading") return <Skeleton className="h-40 w-full" />;
  if (state.status === "error")
    return (
      <Alert
        title={t("loadFailed")}
        action={
          <Button variant="ghost" onClick={reload}>
            {t("retry")}
          </Button>
        }
      />
    );
  const { data } = state;
  if (isUnchosen(data))
    return me.role === "adult" ? (
      <AdventureStart
        familyId={me.family_id}
        onStarted={(outcome) => {
          setTyped(false);
          setTaken(outcome === "taken");
          reload();
        }}
        onPoll={poll}
        onTyping={setTyped}
      />
    ) : (
      <WorldWait me={me} onPoll={poll} />
    );
  return (
    <Story
      taken={typed || taken}
      me={me}
      data={data}
      paused={paused}
      slow={slow}
      slowChapterIds={slowChapterIds}
      reload={reload}
    />
  );
}

export function Adventure() {
  const t = useTranslations("adventure");
  const me = useMe();
  return (
    <Gate state={me}>
      {(m) => (
        <div className="flex flex-col gap-4 pb-6 has-[[data-testid=quest-action-bar]]:pb-24">
          <h1 className="font-display text-2xl font-semibold">{t("title")}</h1>
          <Screen me={m} />
        </div>
      )}
    </Gate>
  );
}
