"use client";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { useRouter } from "@/i18n/navigation";
import { deleteFamily, type Member } from "@/lib/api";
import { errorKey } from "@/lib/errors";
import { inputCls } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/** Owner-only, irreversible: a fixed localized word must be typed first. */
export function FamilyDelete({ me }: { me: Member }) {
  const t = useTranslations("erase");
  const te = useTranslations("errors");
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const phrase = t("fallback");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await deleteFamily(me.family_id);
      router.replace("/");
    } catch (err) {
      setFailure(te(errorKey(err)));
      setBusy(false);
    }
  }

  if (!asking)
    return (
      <Button variant="ghost" onClick={() => setAsking(true)} className="self-start">
        {t("button")}
      </Button>
    );
  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-3 rounded-3xl border border-danger p-5"
    >
      <h2 className="font-display text-xl font-semibold">{t("heading")}</h2>
      <p id="del-hint" className="text-muted">{t("hint", { phrase })}</p>
      <label htmlFor="del-phrase" className="text-[0.95rem] font-semibold">
        {t("label")}
      </label>
      <input
        id="del-phrase"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        aria-describedby="del-hint"
        autoFocus
        autoComplete="off"
        className={inputCls}
      />
      {failure && <Alert>{failure}</Alert>}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={busy || typed.trim() !== phrase}>
          {t("confirm")}
        </Button>
        <Button variant="ghost" onClick={() => setAsking(false)} disabled={busy}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
