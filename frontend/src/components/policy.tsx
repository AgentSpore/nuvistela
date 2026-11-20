import { Fragment, type ReactNode } from "react";
import { z } from "zod";

export const policySectionsSchema = z.array(
  z.object({ h: z.string(), p: z.array(z.string()) }),
);
export type PolicySection = z.infer<typeof policySectionsSchema>[number];

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`)/;

/** Policy strings are plain text with two marks: `**bold**` and `` `code` ``. */
function Inline({ text }: { text: string }) {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`"))
      return (
        <code key={i} className="rounded bg-sunken px-1.5 py-0.5 text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      );
    return <Fragment key={i}>{part}</Fragment>;
  });
}

const isBullet = (line: string) => line.startsWith("- ");

/** Consecutive `- ` lines become one list; everything else is a paragraph. */
function blocks(lines: string[]): ReactNode[] {
  const out: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length === 0) return;
    const items = list;
    list = [];
    out.push(
      <ul key={`ul${out.length}`} className="list-disc space-y-2 pl-6">
        {items.map((line, i) => (
          <li key={i}>
            <Inline text={line} />
          </li>
        ))}
      </ul>,
    );
  };
  for (const line of lines) {
    if (isBullet(line)) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    out.push(
      <p key={`p${out.length}`}>
        <Inline text={line} />
      </p>,
    );
  }
  flush();
  return out;
}

export function Policy({ sections }: { sections: PolicySection[] }) {
  return (
    <>
      {sections.map((s) => (
        <section key={s.h} className="mt-8 flex flex-col gap-3 leading-relaxed">
          <h2 className="font-display text-xl font-semibold break-words sm:text-2xl">{s.h}</h2>
          {blocks(s.p)}
        </section>
      ))}
    </>
  );
}
