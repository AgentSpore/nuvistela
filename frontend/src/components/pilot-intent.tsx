"use client";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import type { PilotIntent } from "@/lib/pilot-events";

export function PilotIntentChoice({
  intent,
  onChange,
}: {
  intent: PilotIntent;
  onChange: (intent: PilotIntent) => void;
}) {
  const t = useTranslations("landing.demo");
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="font-semibold">{t("intentLabel")}</legend>
      <div className="flex flex-wrap gap-3">
        {(["solo", "family"] as const).map((value) => (
          <Button
            key={value}
            variant={intent === value ? "primary" : "ghost"}
            aria-pressed={intent === value}
            onClick={() => onChange(value)}
          >
            {t(value)}
          </Button>
        ))}
      </div>
    </fieldset>
  );
}
