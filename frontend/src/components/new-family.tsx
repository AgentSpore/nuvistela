"use client";
import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { Link as IntlLink } from "@/i18n/navigation";
import { createFamily, type Invite } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { check, familySchema, parseInterests, type FieldErrors } from "@/lib/forms";
import { showErrors, TextField } from "@/components/fields";
import { InviteLink, toLink, type Link } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { cardCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClass } from "@/components/ui/button";

const FIELD_IDS = { title: "f-title", display_name: "f-name", interests: "f-interests" };

function Steps({ current }: { current: 1 | 2 }) {
  const t = useTranslations("new");
  return (
    <ol
      aria-label={t("stepsLabel")}
      className="mb-6 flex items-center gap-3 text-sm font-semibold"
    >
      {([1, 2] as const).map((n) => (
        <li
          key={n}
          aria-current={n === current ? "step" : undefined}
          className={`flex items-center gap-2 ${n === current ? "text-ink" : "text-muted"}`}
        >
          <span
            aria-hidden="true"
            className={`inline-flex size-7 items-center justify-center rounded-full border ${n <= current ? "border-honey-deep bg-honey text-honey-ink" : "border-line-strong"}`}
          >
            {n}
          </span>
          {t(`step${n}`)}
          {n === 1 && (
            <span aria-hidden="true" className="ml-1 h-px w-8 bg-line-strong" />
          )}
        </li>
      ))}
    </ol>
  );
}

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
    if (!r.ok) return showErrors(setErrors, r.errors, FIELD_IDS);
    setErrors({});
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
    <div className="flex flex-col">
      <Steps current={familyId === null ? 1 : 2} />
      <h1 className="font-display text-3xl font-bold sm:text-4xl">
        {familyId === null ? t("heading") : t("createdHeading")}
      </h1>
      <p className="mt-2 mb-6 max-w-[52ch] text-muted">
        {familyId === null ? t("intro") : t("addMore")}
      </p>
      {failure && (
        <div className="mb-5">
          <Alert>{failure}</Alert>
        </div>
      )}
      {familyId === null ? (
        <form onSubmit={submit} noValidate className={`${cardCls} flex flex-col gap-5`}>
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
          <Button
            type="submit"
            disabled={busy}
            aria-busy={busy}
            className="mt-1 w-full sm:w-auto sm:self-start"
          >
            {t("submit")}
          </Button>
        </form>
      ) : (
        <div className="flex flex-col gap-6">
          <section aria-labelledby="links-h" className={cardCls}>
            <h2 id="links-h" className="font-display text-xl font-semibold">
              {t("linksHeading")}
            </h2>
            <p className="mt-1 mb-5 text-muted">{t("linksHint")}</p>
            <ul className="flex flex-col gap-5">
              {links.map((l) => (
                <InviteLink key={l.id} id={l.id} name={l.name} url={l.url} />
              ))}
            </ul>
          </section>
          <div className={cardCls}>
            <MemberForm familyId={familyId} onAdded={added} />
          </div>
          <IntlLink href="/play" className={buttonClass("ghost", "self-start")}>
            {t("play")}
          </IntlLink>
        </div>
      )}
    </div>
  );
}
