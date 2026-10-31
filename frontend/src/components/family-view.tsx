"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { absoluteInvite, reissueInvite, type Member } from "@/lib/api";
import { familyRoster } from "@/lib/roster";
import { errorKey, useMe } from "@/lib/use-me";
import { Gate } from "@/components/gate";
import { InviteLink } from "@/components/invite-link";
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
          <button type="button" onClick={reissue} className={btnGhostCls}>
            {t("reissue")}
            <span className="sr-only"> {member.display_name}</span>
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

export function FamilyView() {
  const t = useTranslations("family");
  const me = useMe();
  return (
    <Gate state={me}>
      {(m) => (
        <section aria-labelledby="fam-h" className="flex flex-col gap-4">
          <h1 id="fam-h" className="text-2xl font-bold">
            {t("title")}
          </h1>
          <ul className="flex flex-col gap-3">
            {familyRoster(m).map((x) => (
              <MemberRow key={x.id} member={x} canReissue={m.role === "adult"} />
            ))}
          </ul>
        </section>
      )}
    </Gate>
  );
}
