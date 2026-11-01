"use client";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { absoluteInvite, reissueInvite, type Invite, type Member } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { canReissue } from "@/lib/reissue";
import { useMe, useMembers } from "@/lib/use-me";
import { Gate } from "@/components/gate";
import { InviteLink, toLink, type Link } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { cardCls } from "@/components/styles";
import { TelegramCard } from "@/components/telegram-card";
import { Alert } from "@/components/ui/alert";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { CrownIcon, RefreshIcon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";

type RowProps = { member: Member; isSelf: boolean; canReissue: boolean };

function MemberRow({ member, isSelf, canReissue: allowed }: RowProps) {
  const t = useTranslations("family");
  const tm = useTranslations("member");
  const te = useTranslations("errors");
  const [url, setUrl] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function reissue() {
    setFailure(null);
    setBusy(true);
    try {
      setUrl(absoluteInvite((await reissueInvite(member.id)).invite_url));
    } catch (err) {
      setFailure(te(errorKey(err)));
    }
    setBusy(false);
  }
  return (
    <li className={`${cardCls} flex flex-col gap-4 !p-4 sm:!p-5`}>
      <div className="flex items-center gap-3.5">
        <Avatar id={member.id} name={member.display_name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg leading-tight font-semibold">
            {member.display_name}
          </p>
          <p className="mt-0.5 text-sm text-muted">
            {member.role === "adult"
              ? tm("roles.adult")
              : `${tm("roles.child")}, ${tm(`bands.${member.age_band}`)}`}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {member.is_owner && (
            <Chip tone="honey">
              <CrownIcon />
              {t("owner")}
            </Chip>
          )}
          {isSelf && <Chip>{t("you")}</Chip>}
        </div>
      </div>
      {allowed && (
        <div>
          <Button
            variant="ghost"
            onClick={reissue}
            disabled={busy}
            aria-label={t("reissueFor", { name: member.display_name })}
            className="min-h-11 py-1.5"
          >
            <RefreshIcon />
            {t("reissue")}
          </Button>
        </div>
      )}
      {url && (
        <ul className="flex flex-col gap-1">
          <InviteLink id={member.id} name={member.display_name} url={url} />
        </ul>
      )}
      {url && <p className="text-sm text-muted">{t("reissued")}</p>}
      {failure && <Alert>{failure}</Alert>}
    </li>
  );
}

function RosterSkeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-3">
      <Skeleton className="h-20 w-full !rounded-3xl" />
      <Skeleton className="h-20 w-full !rounded-3xl" />
    </div>
  );
}

function Roster({ me }: { me: Member }) {
  const t = useTranslations("family");
  const format = useFormatter();
  const { members, failed, loaded, reload } = useMembers(me.family_id);
  const [links, setLinks] = useState<Link[]>([]);
  const added = (invite: Invite) => {
    setLinks((l) => [...l, toLink(invite)]);
    reload();
  };
  const adult = me.role === "adult";
  return (
    <section aria-labelledby="fam-h" className="flex flex-col gap-6 pt-2 sm:pt-6">
      <div>
        <h1 id="fam-h" className="font-display text-3xl font-bold sm:text-4xl">
          {t("title")}
        </h1>
        {loaded && (
          <p className="mt-1 text-muted">
            {t("subtitle", { count: format.number(members.length) })}
          </p>
        )}
      </div>
      {failed && (
        <Alert
          title={t("loadFailed")}
          action={
            <Button variant="ghost" onClick={reload}>
              {t("retry")}
            </Button>
          }
        />
      )}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        {!loaded && !failed ? (
          <RosterSkeleton />
        ) : (
          <ul className="flex flex-col gap-3">
            {members.map((x) => (
              <MemberRow
                key={x.id}
                member={x}
                isSelf={x.id === me.id}
                canReissue={canReissue(me, x)}
              />
            ))}
          </ul>
        )}
        {adult && (
          <div className="flex flex-col gap-6">
            <div className={cardCls}>
              {links.length > 0 && (
                <>
                  <h2 className="mb-4 font-display text-xl font-semibold">
                    {t("invitesHeading")}
                  </h2>
                  <ul className="mb-6 flex flex-col gap-4 border-b border-line pb-6">
                    {links.map((l) => (
                      <InviteLink key={l.id} id={l.id} name={l.name} url={l.url} />
                    ))}
                  </ul>
                </>
              )}
              <MemberForm familyId={me.family_id} onAdded={added} />
            </div>
            <TelegramCard familyId={me.family_id} />
          </div>
        )}
      </div>
    </section>
  );
}

export function FamilyView() {
  const me = useMe();
  return <Gate state={me}>{(m) => <Roster me={m} />}</Gate>;
}
