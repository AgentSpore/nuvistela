"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { showErrors, SelectField, TextField } from "@/components/fields";
import { focusRing } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  isEmail,
  joinWaitlist,
  KIDS_BANDS,
  waitlistErrorKey,
  type KidsBand,
  type WaitlistErrorKey,
} from "@/lib/waitlist";

const SIZES = Array.from({ length: 12 }, (_, i) => i + 1);

function AgeChips({
  bands,
  onToggle,
}: {
  bands: KidsBand[];
  onToggle: (b: KidsBand) => void;
}) {
  const t = useTranslations("waitlist");
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[0.95rem] font-semibold">{t("ages")}</legend>
      <div className="flex flex-wrap gap-2">
        {KIDS_BANDS.map((b) => (
          <button
            key={b}
            type="button"
            aria-pressed={bands.includes(b)}
            onClick={() => onToggle(b)}
            className={`min-h-11 rounded-full border px-4 font-medium transition-colors duration-150 ${focusRing} ${
              bands.includes(b)
                ? "border-honey-deep bg-honey text-honey-ink"
                : "border-line-strong bg-card text-ink hover:bg-sunken"
            }`}
          >
            {t(`bands.${b}`)}
          </button>
        ))}
      </div>
      <p className="text-sm text-muted">{t("agesHint")}</p>
    </fieldset>
  );
}

function useWaitlistSubmit(fields: { email: string; size: string; bands: KidsBand[] }) {
  const t = useTranslations("waitlist");
  const locale = useLocale();
  const [emailError, setEmailError] = useState<string>();
  const [failure, setFailure] = useState<WaitlistErrorKey>();
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const value = fields.email.trim();
    setFailure(undefined);
    if (!isEmail(value)) {
      showErrors(
        (x) => setEmailError(x.email),
        { email: t("invalidEmail") },
        { email: "wl-email" },
      );
      return;
    }
    setEmailError(undefined);
    setPending(true);
    try {
      await joinWaitlist({
        email: value,
        family_size: Number(fields.size),
        kids_age_bands: KIDS_BANDS.filter((b) => fields.bands.includes(b)),
        locale,
      });
      setDone(true);
    } catch (err) {
      setFailure(waitlistErrorKey(err));
    } finally {
      setPending(false);
    }
  }
  return { submit, emailError, failure, pending, done };
}

export function WaitlistForm() {
  const t = useTranslations("waitlist");
  const [email, setEmail] = useState("");
  const [size, setSize] = useState("4");
  const [bands, setBands] = useState<KidsBand[]>([]);
  const { submit, emailError, failure, pending, done } = useWaitlistSubmit({
    email,
    size,
    bands,
  });

  const toggle = (b: KidsBand) =>
    setBands((cur) => (cur.includes(b) ? cur.filter((x) => x !== b) : [...cur, b]));

  if (done)
    return (
      <Alert tone="ok" title={t("ok.title")}>
        {t("ok.body")}
      </Alert>
    );

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-5">
      <TextField
        id="wl-email"
        type="email"
        autoComplete="email"
        label={t("email")}
        hint={t("emailHint")}
        value={email}
        onChange={setEmail}
        maxLength={254}
        error={emailError}
      />
      <SelectField
        id="wl-size"
        label={t("size")}
        value={size}
        onChange={setSize}
        options={SIZES.map((n) => ({ value: String(n), label: t("sizeOption", { n }) }))}
      />
      <AgeChips bands={bands} onToggle={toggle} />
      {failure && <Alert tone="danger">{t(`err.${failure}`)}</Alert>}
      <Button type="submit" disabled={pending} className="text-lg">
        {pending ? t("sending") : t("submit")}
      </Button>
    </form>
  );
}
