"use client";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";
import { Link as IntlLink } from "@/i18n/navigation";
import { createFamily, type Invite } from "@/lib/api";
import { pilotAttribution } from "@/lib/pilot-events";
import { admissionKey, errorKey } from "@/lib/errors";
import { check, familySchema, parseInterests, type FieldErrors } from "@/lib/forms";
import { showErrors, TextField } from "@/components/fields";
import { InviteLink, InviteOnceNote, toLink, type Link } from "@/components/invite-link";
import { MemberForm } from "@/components/member-form";
import { cardCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button, buttonClass } from "@/components/ui/button";

const FIELD_IDS = { title: "f-title", display_name: "f-name", interests: "f-interests" };

/** Step 2 is named for what the creator really gets: links only when someone else is invited. */
function Steps({ current, shared }: { current: 1 | 2; shared: boolean }) {
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
          {n === 1 ? t("step1") : t(shared ? "step2" : "step2Solo")}
          {n === 1 && (
            <span aria-hidden="true" className="ml-1 h-px w-8 bg-line-strong" />
          )}
        </li>
      ))}
    </ol>
  );
}

type Values = { title: string; name: string; interests: string };
type FieldsProps = {
  v: Values;
  set: (k: keyof Values) => (val: string) => void;
  err: (k: string) => string | undefined;
  busy: boolean;
  consent: boolean;
  onConsent: (v: boolean) => void;
};

function ConsentBox({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  const t = useTranslations("new");
  return (
    <label htmlFor="f-consent" className="flex items-start gap-3 text-[0.95rem]">
      <input
        id="f-consent"
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-6 shrink-0 accent-[var(--color-honey-deep)]"
      />
      <span id="f-consent-text">
        {t.rich("consent", {
          policy: (chunks) => (
            <IntlLink
              href="/privacy"
              target="_blank"
              className="underline underline-offset-2"
            >
              {chunks}
            </IntlLink>
          ),
        })}
      </span>
    </label>
  );
}

function FamilyFields({ v, set, err, busy, consent, onConsent }: FieldsProps) {
  const t = useTranslations("new");
  return (
    <>
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
      <ConsentBox checked={consent} onChange={onConsent} />
      <Button
        type="submit"
        disabled={busy || !consent}
        aria-describedby={consent ? undefined : "f-consent-text"}
        aria-busy={busy}
        className="mt-1 w-full sm:w-auto sm:self-start"
      >
        {t("submit")}
      </Button>
    </>
  );
}

type Created = Invite & { family_id: string };

function FamilyForm({ onCreated }: { onCreated: (created: Created) => void }) {
  const te = useTranslations("errors");
  const locale = useLocale();
  const [v, setV] = useState({ title: "", name: "", interests: "" });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const set = (k: keyof typeof v) => (val: string) => setV((p) => ({ ...p, [k]: val }));
  const err = (k: string) => (errors[k] ? te(errors[k]) : undefined);

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
      onCreated(
        await createFamily({
          ...r.data,
          locale,
          privacy_consent: true,
          attribution: pilotAttribution(null),
        }),
      );
    } catch (err) {
      setFailure(te(admissionKey(err) ?? errorKey(err)));
      setBusy(false);
    }
  }

  return (
    <>
      {failure && (
        <div className="mb-5">
          <Alert>{failure}</Alert>
        </div>
      )}
      <form onSubmit={submit} noValidate className={`${cardCls} flex flex-col gap-5`}>
        <FamilyFields
          v={v}
          set={set}
          err={err}
          busy={busy}
          consent={consent}
          onConsent={setConsent}
        />
      </form>
    </>
  );
}

function LinksCard({ links }: { links: Link[] }) {
  const t = useTranslations("new");
  return (
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
      <div className="mt-5">
        <InviteOnceNote />
      </div>
    </section>
  );
}

type CreatedProps = { familyId: string; links: Link[]; onAdded: (i: Invite) => void };

function CreatedView({ familyId, links, onAdded }: CreatedProps) {
  const t = useTranslations("new");
  const [adding, setAdding] = useState(false);
  const [announced, setAnnounced] = useState<Link | null>(null);
  const addedOnce = announced !== null;
  useEffect(() => {
    if (adding) document.getElementById("m-name")?.focus();
    else if (addedOnce) document.getElementById("add-member")?.focus();
  }, [adding, addedOnce]);
  const added = (invite: Invite) => {
    onAdded(invite);
    setAdding(false);
    setAnnounced(toLink(invite));
  };
  // A player alone goes straight to the world; links matter once someone else is invited.
  const shared = links.length > 1;
  return (
    <div className="flex flex-col gap-6">
      {shared && <LinksCard links={links} />}
      <p role="status" className="sr-only">
        {/* A fresh node per invite: the same name twice still changes the region. */}
        {announced && (
          <span key={announced.id}>{t("linkReady", { name: announced.name })}</span>
        )}
      </p>
      <IntlLink
        href="/adventure"
        className={buttonClass("primary", "w-full sm:w-auto sm:self-start")}
      >
        {t("play")}
      </IntlLink>
      {adding ? (
        <div className={cardCls}>
          <MemberForm familyId={familyId} onAdded={added} />
        </div>
      ) : (
        <Button
          id="add-member"
          variant="ghost"
          onClick={() => setAdding(true)}
          className="w-full sm:w-auto sm:self-start"
        >
          {t(addedOnce ? "addAnother" : "addMember")}
        </Button>
      )}
    </div>
  );
}

export function NewFamily() {
  const t = useTranslations("new");
  const [familyId, setFamilyId] = useState<string | null>(null);
  const [links, setLinks] = useState<Link[]>([]);
  const added = (invite: Invite) => setLinks((l) => [...l, toLink(invite)]);
  const created = (invite: Created) => {
    added(invite);
    setFamilyId(invite.family_id);
  };
  const open = familyId === null;
  return (
    <div className="flex flex-col">
      <Steps current={open ? 1 : 2} shared={links.length > 1} />
      <h1 className="font-display text-3xl font-bold sm:text-4xl">
        {open ? t("heading") : t("createdHeading")}
      </h1>
      <p className="mt-2 mb-6 max-w-[52ch] text-muted">
        {open ? t("intro") : t("addMore")}
      </p>
      {open ? (
        <FamilyForm onCreated={created} />
      ) : (
        <CreatedView familyId={familyId} links={links} onAdded={added} />
      )}
    </div>
  );
}
