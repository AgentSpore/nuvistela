import type { ReactNode } from "react";
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
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-medium">
        {label}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} className="text-sm font-medium text-danger">
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
        className={inputCls}
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
