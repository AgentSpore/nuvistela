"use client";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { addMember, AGE_BANDS, type Invite } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { check, memberInputSchema, parseInterests, type FieldErrors } from "@/lib/forms";
import { showErrors, SelectField, TextField } from "@/components/fields";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type Props = { familyId: string; onAdded: (invite: Invite) => void };

const FIELD_IDS = {
  display_name: "m-name",
  age_band: "m-band",
  interests: "m-interests",
};
const EMPTY = { name: "", band: "adult", interests: "" };

// INVARIANT: the API only accepts the adult role for the adult band, so role is derived, never asked.
const roleFor = (band: string) => (band === "adult" ? "adult" : "child");

export function MemberForm({ familyId, onAdded }: Props) {
  const t = useTranslations("member");
  const te = useTranslations("errors");
  const [v, setV] = useState(EMPTY);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (val: string) => setV((p) => ({ ...p, [k]: val }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = check(memberInputSchema, {
      display_name: v.name,
      age_band: v.band,
      role: roleFor(v.band),
      interests: parseInterests(v.interests),
    });
    if (!r.ok) return showErrors(setErrors, r.errors, FIELD_IDS);
    setErrors({});
    setBusy(true);
    setFailure(null);
    try {
      const invite = await addMember(familyId, r.data);
      onAdded(invite);
      setV(EMPTY);
    } catch (err) {
      setFailure(te(errorKey(err)));
    }
    setBusy(false);
  }

  const err = (k: string) => (errors[k] ? te(errors[k]) : undefined);
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <h2 className="font-display text-xl font-semibold">{t("heading")}</h2>
      <TextField
        id="m-name"
        label={t("name")}
        value={v.name}
        onChange={set("name")}
        maxLength={40}
        error={err("display_name")}
      />
      <SelectField
        id="m-band"
        label={t("band")}
        value={v.band}
        onChange={set("band")}
        error={err("age_band")}
        options={AGE_BANDS.map((b) => ({ value: b, label: t(`bands.${b}`) }))}
      />
      <TextField
        id="m-interests"
        label={t("interests")}
        hint={t("interestsHint")}
        value={v.interests}
        onChange={set("interests")}
        error={err("interests")}
      />
      {failure && <Alert>{failure}</Alert>}
      <Button type="submit" disabled={busy} aria-busy={busy}>
        {t("submit")}
      </Button>
    </form>
  );
}
