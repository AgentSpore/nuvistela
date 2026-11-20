"use client";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";
import type {
  ChronicleEntry,
  Cover,
  Scene,
  WorldStatus,
  WorldView,
} from "@/lib/adventure-api";
import { useFreshMilestones } from "@/lib/milestones-seen";
import { useWorld } from "@/lib/use-world";
import { cardCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { World3d } from "@/components/world-3d";
import { WorldChronicle } from "@/components/world-chronicle";
import { WorldCover } from "@/components/world-cover";
import { WorldShare } from "@/components/world-share";
import { WorldWriting } from "@/components/world-writing";

const NONE: never[] = [];

type Props = {
  familyId: string;
  status: WorldStatus;
  memberId: string;
  firstVisit: boolean;
  slow: boolean;
  chronicle?: ChronicleEntry[];
  skills?: string[];
  /** What follows the world on the screen; held back until the world has loaded so it is never pushed down. */
  children?: ReactNode;
};

function Waiting({ familyId, slow }: { familyId: string; slow: boolean }) {
  const t = useTranslations("adventure.world");
  return (
    <section
      role="status"
      className={`${cardCls} relative flex flex-col items-center gap-3 overflow-hidden text-center`}
    >
      <WorldWriting familyId={familyId} />
      {slow && (
        <Alert tone="info" live={false}>
          {t("slow")}
        </Alert>
      )}
    </section>
  );
}

function Hero({ world, memberId }: { world: WorldView; memberId: string }) {
  const t = useTranslations("adventure.world");
  const tc = useTranslations("common");
  const hero = world.heroes.find((h) => h.member_id === memberId);
  if (!hero) return null;
  return (
    <div className="rounded-2xl bg-honey-soft p-4">
      <p className="text-sm font-semibold text-muted">{t("hero")}</p>
      <p className="font-display text-xl font-semibold">{hero.hero_class}</p>
      <p>
        {tc.rich("labelValueStyled", {
          label: t("trait"),
          value: hero.trait,
          v: (chunks) => <span className="font-semibold">{chunks}</span>,
        })}
      </p>
      <p>
        {tc.rich("labelValueStyled", {
          label: t("skill"),
          value: hero.skill,
          v: (chunks) => <span className="font-semibold">{chunks}</span>,
        })}
      </p>
    </div>
  );
}

/** Closed by default: five place cards would push the first quest several screens down. */
function Places({ locations }: { locations: WorldView["locations"] }) {
  const t = useTranslations("adventure.world");
  return (
    <details>
      <summary className="cursor-pointer">
        <h3 className="inline font-semibold">
          {t("places")} · {locations.length}
        </h3>
      </summary>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2">
        {locations.map((l) => (
          <li key={l.name} className="rounded-2xl border border-line p-3">
            <p className="font-semibold">{l.name}</p>
            <p className="text-sm text-muted">{l.description}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Holds the world card's place, picture box included, while the world is fetched. */
function Loading() {
  return (
    <div className={`${cardCls} flex flex-col gap-4`}>
      <Skeleton className="aspect-[2/1] w-full md:aspect-[5/2]" />
      <Skeleton className="h-7 w-2/3" />
    </div>
  );
}

type PartProps = Omit<Props, "status" | "slow" | "children" | "chronicle" | "skills"> & {
  chronicle: ChronicleEntry[];
  skills: string[];
  world: WorldView;
  genre: string;
  cover: Cover | null;
  growing: boolean;
  scene: Scene | null;
};

/**
 * Cover and title only: the quest follows at once. The cover size is fixed at mount so the first chapter never resizes it.
 * The walk sits on the cover only once the family's own scene is ready; the library world stays in «О мире».
 */
function Top({ familyId, world, genre, cover, growing, firstVisit, scene }: PartProps) {
  const t = useTranslations("adventure.world");
  const [compact] = useState(!firstVisit);
  return (
    <section className={cardCls}>
      <WorldCover
        familyId={familyId}
        cover={cover}
        growing={growing}
        genre={genre}
        title={world.title}
        compact={compact}
        action={
          scene && <World3d genre={genre} scene={scene} corner className="shadow-soft" />
        }
        topAction={<WorldShare familyId={familyId} cover={cover} />}
      />
      <h2 className="font-display text-xl font-semibold">
        <span className="sr-only">{t("heading")}: </span>
        {world.title}
      </h2>
    </section>
  );
}

/**
 * Open while there is no chapter yet, closed on a return so the quest and the story stay in reach.
 * It is the last block, so closing it when the first check-in is sent moves nothing above it.
 */
function About(p: PartProps) {
  const { world, genre, scene, memberId, firstVisit, chronicle, skills, familyId } = p;
  const t = useTranslations("adventure.world");
  const { fresh, observe } = useFreshMilestones(familyId, chronicle);
  const [chosen, setChosen] = useState<boolean | null>(null);
  const open = chosen ?? (firstVisit || fresh.size > 0);
  return (
    <details
      open={open}
      onToggle={(e) => e.currentTarget.open !== open && setChosen(e.currentTarget.open)}
      className={cardCls}
    >
      <summary className="cursor-pointer font-display text-xl font-semibold">
        {t("about")}
      </summary>
      <div className="mt-3 flex flex-col gap-4">
        <div className="flex">
          <World3d genre={genre} scene={scene} />
        </div>
        <p className="text-muted">{world.setting}</p>
        <p className="whitespace-pre-line">{world.prologue}</p>
        <Hero world={world} memberId={memberId} />
        <WorldChronicle
          chronicle={chronicle}
          skills={skills}
          fresh={fresh}
          observe={observe}
        />
        <Places locations={world.locations} />
      </div>
    </details>
  );
}

export function WorldPanel({
  familyId,
  status,
  memberId,
  firstVisit,
  slow,
  chronicle = NONE,
  skills = NONE,
  children,
}: Props) {
  const t = useTranslations("adventure");
  const { world, genre, cover, growing, scene, failed, erred, retry } = useWorld(
    familyId,
    status,
    chronicle.length,
  );
  if (status === "pending")
    return (
      <>
        <Waiting familyId={familyId} slow={slow} />
        {children}
      </>
    );
  if (failed)
    return (
      <>
        <Alert
          title={t("world.loadFailed")}
          action={
            <Button variant="ghost" onClick={retry}>
              {t("retry")}
            </Button>
          }
        />
        {children}
      </>
    );
  if (!world) return erred ? children : <Loading />;
  const part = {
    familyId,
    world,
    genre,
    cover,
    growing,
    scene,
    memberId,
    firstVisit,
    chronicle,
    skills,
  };
  return (
    <>
      <Top {...part} />
      {children}
      <About {...part} />
    </>
  );
}
