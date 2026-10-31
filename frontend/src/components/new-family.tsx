"use client";
import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { createFamily, type Invite } from "@/lib/api";
import { check, familySchema, parseInterests, type FieldErrors } from "@/lib/forms";
import { errorKey } from "@/lib/use-me";
import { focusFirstError, TextField } from "@/components/fields";
import { InviteLink, toLink, type Link } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { btnCls, cardCls } from "@/components/styles";

const FIELD_IDS = { title: "f-title", display_name: "f-name", interests: "f-interests" };

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
  const added = (invite: Invite) => setLinks((l) => [...l, toLink(invite)]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = check(familySchema, {
      title: v.title,
      display_name: v.name,
      interests: parseInterests(v.interests),
    });
    setErrors(r.ok ? {} : r.errors);
    if (!r.ok) return focusFirstError(r.errors, FIELD_IDS);
    setBusy(true);
    setFailure(null);
    try {
      const created = await createFamily({ ...r.data, locale });
      added(created);
      setFamilyId(created.family_id);
    } catch (err) {
      setFailure(te(errorKey(err)));
    }
    setBusy(false);
  }

  const err = (k: string) => (errors[k] ? te(errors[k]) : undefined);
  return (
    <div className="flex flex-col gap-6">
      {failure && (
        <p role="alert" className="font-medium text-danger">
          {failure}
        </p>
      )}
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
