// Example images ship as pre-resized files next to the original (`name.webp`
// is 768px wide, `name-360.webp` and `name-640.webp` are the smaller copies).
// There is no image optimizer behind the standalone server, so the srcset
// points straight at these files.
// The 360px copy also serves Next's 384px srcset slot, the closest one above it.
const VARIANTS = [
  { upTo: 384, file: 360 },
  { upTo: 640, file: 640 },
] as const;

export function exampleLoader({ src, width }: { src: string; width: number }): string {
  const variant = VARIANTS.find((v) => width <= v.upTo);
  return variant ? src.replace(/\.webp$/, `-${variant.file}.webp`) : src;
}
