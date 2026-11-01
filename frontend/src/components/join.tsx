"use client";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { Link, useRouter } from "@/i18n/navigation";
import { acceptInvite, ApiError } from "@/lib/api";
import { buttonClass } from "@/components/ui/button";

/** 401: invalid, expired or used token; 422: malformed (e.g. oversized) token. */
const REJECTED = new Set([401, 422]);

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
        setState(e instanceof ApiError && REJECTED.has(e.status) ? "invalid" : "failed"),
    );
  }, [router]);

  if (state === "working")
    return (
      <div role="status" className="flex flex-col items-center gap-4 pt-10 text-center">
        <span
          aria-hidden="true"
          className="size-10 animate-spin rounded-full border-4 border-line border-t-honey-deep"
        />
        <h1 className="font-display text-xl font-semibold">{t("working")}</h1>
      </div>
    );
  return (
    <div
      role="alert"
      className="rise rounded-3xl border border-line bg-card p-7 shadow-soft sm:p-9"
    >
      <h1 className="font-display text-2xl font-semibold">
        {t(state === "invalid" ? "invalidTitle" : "failedTitle")}
      </h1>
      <p className="mt-2 text-muted">{t(state)}</p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link
          href="/new"
          className={buttonClass(state === "failed" ? "ghost" : "primary")}
        >
          {t("create")}
        </Link>
      </div>
    </div>
  );
}
