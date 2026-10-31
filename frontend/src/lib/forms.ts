import { z } from "zod";
import { AGE_BANDS, ROLES } from "@/lib/api";

const name = z.string().trim().min(1, "required").max(40, "tooLong");
const interests = z
  .array(z.string().trim().min(1).max(30, "tagTooLong"))
  .max(10, "tooMany");

export const familySchema = z.object({
  title: z.string().trim().min(1, "required").max(80, "tooLong"),
  display_name: name,
  interests,
});

export const memberInputSchema = z
  .object({
    display_name: name,
    age_band: z.enum(AGE_BANDS),
    role: z.enum(ROLES),
    interests,
  })
  .refine((m) => (m.role === "adult") === (m.age_band === "adult"), {
    path: ["role"],
    message: "roleMismatch",
  });

export const parseInterests = (raw: string): string[] =>
  raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

export type FieldErrors = Record<string, string>;
export type Checked<T> = { ok: true; data: T } | { ok: false; errors: FieldErrors };

/** Maps the first zod issue per field to its message key. */
export function check<S extends z.ZodType>(
  schema: S,
  value: unknown,
): Checked<z.infer<S>> {
  const r = schema.safeParse(value);
  if (r.success) return { ok: true, data: r.data };
  const errors: FieldErrors = {};
  for (const issue of r.error.issues) {
    const field = String(issue.path[0] ?? "form");
    errors[field] ??= issue.message;
  }
  return { ok: false, errors };
}
