"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckIcon, CopyIcon } from "@/components/ui/icons";

export type CopyStatus = "idle" | "copied" | "failed";

const RESET_MS = 2400;

/** Copies `value`; on a denied clipboard calls `onFail` so the caller can select the text. */
export function useCopy(value: string, onFail?: () => void) {
  const [status, setStatus] = useState<CopyStatus>("idle");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(value);
      setStatus("copied");
      timer.current = setTimeout(() => setStatus("idle"), RESET_MS);
    } catch {
      setStatus("failed");
      onFail?.();
    }
  }
  return { status, copy };
}

type Labels = { copy: string; copied: string; failed: string };

export function CopyButton({
  status,
  onCopy,
  labels,
  className,
}: {
  status: CopyStatus;
  onCopy: () => void;
  labels: Labels;
  className?: string;
}) {
  const done = status === "copied";
  return (
    <Button variant="ghost" onClick={onCopy} className={className}>
      {done ? <CheckIcon /> : <CopyIcon />}
      {done ? labels.copied : labels.copy}
    </Button>
  );
}

/** Live region next to a copy button: speaks the result, shows the failure visibly. */
export function CopyStatusText({
  status,
  labels,
}: {
  status: CopyStatus;
  labels: Labels;
}) {
  return (
    <span
      role="status"
      className={status === "failed" ? "text-sm font-semibold text-danger" : "sr-only"}
    >
      {status === "idle" ? "" : status === "copied" ? labels.copied : labels.failed}
    </span>
  );
}
