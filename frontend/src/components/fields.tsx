import type { ReactNode } from "react";
import { flushSync } from "react-dom";
import { inputCls } from "@/components/styles";

type FieldProps = { id: string; label: string; error?: string; hint?: string };
type TextProps = FieldProps & {
  value: string;
  onChange: (v: string) => void;
  maxLength?: number;
};
type SelectProps = FieldProps & {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
};

const describedBy = (id: string, error?: string, hint?: string) =>
  [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(" ") || undefined;

function Wrap({
  id,
  label,
  error,
  hint,
  children,
}: FieldProps & { children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[0.95rem] font-semibold">
        {label}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} className="rise text-sm font-semibold text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({ value, onChange, maxLength, ...f }: TextProps) {
  return (
    <Wrap {...f}>
      <input
        id={f.id}
        value={value}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(f.error)}
        aria-describedby={describedBy(f.id, f.error, f.hint)}
        className={inputCls}
      />
    </Wrap>
  );
}

export function SelectField({ value, onChange, options, ...f }: SelectProps) {
  return (
    <Wrap {...f}>
      <select
        id={f.id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(f.error)}
        aria-describedby={describedBy(f.id, f.error, f.hint)}
        className={`${inputCls} cursor-pointer`}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Wrap>
  );
}

/** Renders the errors, then focuses the first field so it is already described by its error. */
export function showErrors(
  setErrors: (e: Record<string, string>) => void,
  errors: Record<string, string>,
  ids: Record<string, string>,
): void {
  flushSync(() => setErrors(errors));
  const key = Object.keys(errors)[0];
  if (key !== undefined && ids[key] !== undefined)
    document.getElementById(ids[key])?.focus();
}
