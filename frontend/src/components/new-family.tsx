"use client";
import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { absoluteInvite, createFamily, type Invite } from "@/lib/api";
import { check, familySchema, parseInterests, type FieldErrors } from "@/lib/forms";
import { rememberMembers } from "@/lib/roster";
import { errorKey } from "@/lib/use-me";
import { TextField } from "@/components/fields";
import { InviteLink } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { btnCls, cardCls } from "@/components/styles";

type Link = { id: string; name: string; url: string };

export function NewFamily() {
  const t = useTranslations("new");
  const te = useTranslations("errors");
  const locale = useLocale();
  const [v, setV] = useState({ title: "", name: "", interests: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [familyId, setFamilyId] = useState<string | null>(null);
  const [links, setLinks] = useState<Link[]>([]);
  const set = (k: keyof typeof v) => (val: string) => setV((p) => ({ ...p, [k]: val }));

  function added(invite: Invite): void {
    rememberMembers([invite.member]);
    const link = {
      id: invite.member.id,
      name: invite.member.display_name,
      url: absoluteInvite(invite.invite_url),
    };
    setLinks((l) => [...l, link]);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = check(familySchema, {
      title: v.title,
      display_name: v.name,
      interests: parseInterests(v.interests),
    });
    setErrors(r.ok ? {} : r.errors);
    if (!r.ok) return;
    setBusy(true);
    setFailure(null);
    try {
      const created = await createFamily({ ...r.data, locale });
      setFamilyId(created.family_id);
      added(created);
    } catch (err) {
      setFailure(te(errorKey(err)));
    }
    setBusy(false);
  }

  const err = (k: string) => (errors[k] ? te(errors[k]) : undefined);
  return (
    <div className="flex flex-col gap-6">
      {familyId === null ? (
        <form onSubmit={submit} noValidate className={`${cardCls} flex flex-col gap-4`}>
          <TextField
            id="f-title"
            label={t("title")}
            value={v.title}
            onChange={set("title")}
            maxLength={80}
            error={err("title")}
          />
          <TextField
            id="f-name"
            label={t("name")}
            value={v.name}
            onChange={set("name")}
            maxLength={40}
            error={err("display_name")}
          />
          <TextField
            id="f-interests"
            label={t("interests")}
            hint={t("interestsHint")}
            value={v.interests}
            onChange={set("interests")}
            error={err("interests")}
          />
          {failure && (
            <p role="alert" className="font-medium text-danger">
              {failure}
            </p>
          )}
          <button type="submit" disabled={busy} className={btnCls}>
            {t("submit")}
          </button>
        </form>
      ) : (
        <>
          <section aria-labelledby="links-h" className={cardCls}>
            <h2 id="links-h" className="text-xl font-semibold">
              {t("linksHeading")}
            </h2>
            <p className="mt-1 mb-4 text-muted">{t("linksHint")}</p>
            <ul className="flex flex-col gap-4">
              {links.map((l) => (
                <InviteLink key={l.id} name={l.name} url={l.url} />
              ))}
            </ul>
          </section>
          <div className={cardCls}>
            <MemberForm familyId={familyId} onAdded={added} />
          </div>
        </>
      )}
    </div>
  );
}
