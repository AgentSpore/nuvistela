import type { ButtonHTMLAttributes } from "react";
import { focusRing } from "@/components/styles";

export type Variant = "primary" | "ghost" | "quiet";

const BASE = `inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 py-2.5 font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55 ${focusRing}`;
const VARIANT: Record<Variant, string> = {
  primary: "btn-primary bg-honey text-honey-ink hover:bg-honey/90",
  ghost: "border border-line-strong bg-card text-ink hover:bg-sunken",
  quiet: "px-3 text-accent hover:bg-accent-soft",
};

/** Class string for anything styled as a button (links included). */
export const buttonClass = (variant: Variant = "primary", extra = ""): string =>
  `${BASE} ${VARIANT[variant]} ${extra}`.trim();

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant };

export function Button({ variant = "primary", className = "", type, ...rest }: Props) {
  return (
    <button
      type={type ?? "button"}
      className={buttonClass(variant, className)}
      {...rest}
    />
  );
}
