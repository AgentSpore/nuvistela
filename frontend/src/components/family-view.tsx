"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { absoluteInvite, reissueInvite, type Invite, type Member } from "@/lib/api";
import { errorKey, useMe, useMembers } from "@/lib/use-me";
import { Gate } from "@/components/gate";
import { InviteLink, toLink, type Link } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { btnGhostCls, cardCls } from "@/components/styles";

function MemberRow({ member, canReissue }: { member: Member; canReissue: boolean }) {
  const t = useTranslations("family");
  const tm = useTranslations("member");
  const te = useTranslations("errors");
  const [url, setUrl] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  async function reissue() {
    setFailure(null);
    try {
      setUrl(absoluteInvite((await reissueInvite(member.id)).invite_url));
    } catch (err) {
      setFailure(te(errorKey(err)));
    }
  }
  return (
    <li className={`${cardCls} flex flex-col gap-3`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold">{member.display_name}</p>
          <p className="text-sm text-muted">
            {member.role === "adult"
              ? tm("roles.adult")
              : `${tm("roles.child")}, ${tm(`bands.${member.age_band}`)}`}
          </p>
        </div>
        {canReissue && (
          <button
            type="button"
            onClick={reissue}
            aria-label={t("reissueFor", { name: member.display_name })}
            className={btnGhostCls}
          >
            {t("reissue")}
          </button>
        )}
      </div>
      {url && (
        <ul>
          <InviteLink name={member.display_name} url={url} />
        </ul>
      )}
      {url && <p className="text-sm text-muted">{t("reissued")}</p>}
      {failure && (
        <p role="alert" className="font-medium text-danger">
          {failure}
        </p>
      )}
    </li>
  );
}

function Roster({ me }: { me: Member }) {
  const t = useTranslations("family");
  const { members, reload } = useMembers(me.family_id);
  const [links, setLinks] = useState<Link[]>([]);
  const added = (invite: Invite) => {
    setLinks((l) => [...l, toLink(invite)]);
    reload();
  };
  return (
    <section aria-labelledby="fam-h" className="flex flex-col gap-4">
      <h1 id="fam-h" className="text-2xl font-bold">
        {t("title")}
      </h1>
      <ul className="flex flex-col gap-3">
        {members.map((x) => (
          <MemberRow
            key={x.id}
            member={x}
            canReissue={me.role === "adult" && x.id !== me.id}
          />
        ))}
      </ul>
      {me.role === "adult" && (
        <div className={cardCls}>
          {links.length > 0 && (
            <ul className="mb-4 flex flex-col gap-4">
              {links.map((l) => (
                <InviteLink key={l.id} name={l.name} url={l.url} />
              ))}
            </ul>
          )}
          <MemberForm familyId={me.family_id} onAdded={added} />
        </div>
      )}
    </section>
  );
}

export function FamilyView() {
  const me = useMe();
  return <Gate state={me}>{(m) => <Roster me={m} />}</Gate>;
}
