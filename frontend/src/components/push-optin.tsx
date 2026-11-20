"use client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import {
  disablePush,
  enablePush,
  fetchPushKey,
  markDeclined,
  needsHomeScreen,
  pushSupported,
  syncSubscription,
  wasDeclined,
} from "@/lib/push";
import { cardCls, focusRing } from "@/components/styles";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type PushState =
  | { kind: "off" }
  | { kind: "home" }
  | { kind: "ready"; key: string; subscribed: boolean; taken: boolean; failed: boolean };

async function probe(): Promise<PushState> {
  if (needsHomeScreen())
    return (await fetchPushKey()) ? { kind: "home" } : { kind: "off" };
  if (!pushSupported()) return { kind: "off" };
  const [key, saved] = await Promise.all([fetchPushKey(), syncSubscription()]);
  if (!key) return { kind: "off" };
  return {
    kind: "ready",
    key,
    subscribed: saved === "saved",
    taken: saved === "taken",
    failed: saved === "failed",
  };
}

/** Null while checking; `off` also covers a server without keys (feature hidden). */
function usePush() {
  const [state, setState] = useState<PushState | null>(null);
  useEffect(() => {
    let ignore = false;
    probe().then((next) => !ignore && setState(next));
    return () => {
      ignore = true;
    };
  }, []);
  const update = (patch: { subscribed: boolean; taken: boolean; failed: boolean }) =>
    setState((s) => (s?.kind === "ready" ? { ...s, ...patch } : s));
  return { state, update };
}

/** `when`: an adult, after a chapter is ready. Asks first; the browser's prompt follows the tap. */
export function PushOptIn({ when }: { when: boolean }) {
  const canShow =
    when &&
    pushSupported() &&
    !needsHomeScreen() &&
    Notification.permission !== "denied" &&
    !wasDeclined();
  return canShow ? <OptInCard /> : null;
}

function OptInCard() {
  const t = useTranslations("push");
  const { state, update } = usePush();
  const [gone, setGone] = useState(false);
  const [failed, setFailed] = useState<"failed" | "taken" | null>(null);
  if (gone || state?.kind !== "ready" || state.subscribed || state.taken || state.failed)
    return null;
  const { key } = state;
  async function accept() {
    const result = await enablePush(key);
    if (result === "on") return update({ subscribed: true, taken: false, failed: false });
    if (result === "denied") {
      markDeclined();
      return setGone(true);
    }
    setFailed(result);
  }
  function decline() {
    markDeclined();
    setGone(true);
  }
  return (
    <section aria-labelledby="push-q" className={`${cardCls} flex flex-col gap-4`}>
      <h2 id="push-q" className="font-display text-xl font-semibold">
        {t("question")}
      </h2>
      {failed && <Alert>{t(failed)}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button onClick={accept}>{t("yes")}</Button>
        <Button variant="ghost" onClick={decline}>
          {t("no")}
        </Button>
      </div>
    </section>
  );
}

function Switch({
  on,
  busy,
  onClick,
}: {
  on: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  const t = useTranslations("push");
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={t("toggle")}
      disabled={busy}
      onClick={onClick}
      className={`relative h-8 w-14 shrink-0 rounded-full border border-line-strong transition-colors motion-reduce:transition-none ${on ? "bg-accent" : "bg-sunken"} ${focusRing}`}
    >
      <span
        aria-hidden="true"
        className={`absolute top-0.5 left-0.5 size-6 rounded-full bg-card shadow-soft transition-transform motion-reduce:transition-none ${on ? "translate-x-6" : ""}`}
      />
    </button>
  );
}

/** What the mount sync left unresolved, shown until the adult acts. */
function syncNote(state: PushState): "taken" | "failed" | null {
  if (state.kind !== "ready") return null;
  if (state.taken) return "taken";
  return state.failed ? "failed" : null;
}

/** Adults only, on the family page: this device's subscription, on or off. */
export function PushToggle() {
  const t = useTranslations("push");
  const { state, update } = usePush();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<"blocked" | "failed" | "taken" | null>(null);
  if (state?.kind !== "ready" && state?.kind !== "home") return null;
  async function flip(on: boolean, key: string) {
    setBusy(true);
    setNote(null);
    if (on) {
      const result = await enablePush(key);
      if (result === "on") update({ subscribed: true, taken: false, failed: false });
      else setNote(result === "denied" ? "blocked" : result);
    } else if (await disablePush())
      update({ subscribed: false, taken: false, failed: false });
    else setNote("failed");
    setBusy(false);
  }
  const shownNote = note ?? syncNote(state);
  return (
    <section aria-labelledby="push-h" className={`${cardCls} flex flex-col gap-4`}>
      <h2 id="push-h" className="font-display text-xl font-semibold">
        {t("heading")}
      </h2>
      {state.kind === "home" ? (
        <p className="text-muted">{t("homeScreen")}</p>
      ) : (
        <div className="flex items-center justify-between gap-4">
          <p className="min-w-0 flex-1">{t("toggle")}</p>
          <Switch
            on={state.subscribed}
            busy={busy}
            onClick={() => flip(!state.subscribed, state.key)}
          />
        </div>
      )}
      {shownNote && <Alert tone="info">{t(shownNote)}</Alert>}
    </section>
  );
}
