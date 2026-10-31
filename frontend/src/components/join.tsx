"use client";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { acceptInvite, ApiError } from "@/lib/api";

type State = "working" | "invalid" | "failed";

/** Consumes the invite token from the URL fragment: a POST, so link previews cannot burn it. */
export function Join() {
  const t = useTranslations("join");
  const router = useRouter();
  const started = useRef(false);
  const [state, setState] = useState<State>("working");

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = window.location.hash.slice(1);
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
    const attempt = token
      ? acceptInvite(token)
      : Promise.reject(new ApiError("http", 401));
    attempt.then(
      () => router.replace("/play"),
      (e: unknown) =>
        setState(e instanceof ApiError && e.status === 401 ? "invalid" : "failed"),
    );
  }, [router]);

  if (state === "working")
    return (
      <p role="status" className="text-muted">
        {t("working")}
      </p>
    );
  return (
    <div role="alert" className="flex flex-col items-start gap-3">
      <p className="font-medium text-danger">{t(state)}</p>
      <Link
        href="/new"
        className="font-semibold text-accent underline underline-offset-4"
      >
        {t("create")}
      </Link>
    </div>
  );
}
