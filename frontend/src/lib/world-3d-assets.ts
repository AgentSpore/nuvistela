/**
 * Library of pre-made 3D worlds in public/worlds/<id>/. File names carry a content hash so
 * next.config can serve them `immutable`; regenerate this table when an asset changes.
 */
const FILES = {
  "library-nook-full": {
    spz: "world-500k.717d0042e9.spz",
    spzBytes: 8031664,
    pano: "pano.676411e0e4.webp",
    thumb: "thumbnail.435c0a125f.webp",
  },
  "seaside-lighthouse": {
    spz: "world-500k.24700616be.spz",
    spzBytes: 5589644,
    pano: "pano.7ebd90e69b.webp",
    thumb: "thumbnail.03841edf28.webp",
  },
  "sky-islands": {
    spz: "world-500k.986880eee3.spz",
    spzBytes: 5519167,
    pano: "pano.c3e7facd8d.webp",
    thumb: "thumbnail.8ecfdb72aa.webp",
  },
} as const;

type WorldId = keyof typeof FILES;

/** Genre → world. A genre absent here (space) has no 3D button. */
const GENRE_WORLD: Partial<Record<string, WorldId>> = {
  fairy_tale: "library-nook-full",
  pirates: "seaside-lighthouse",
  custom: "sky-islands",
};

/**
 * gzip size of the lazy three + Spark chunks (`pnpm build`, 2026-11-12: 1,163,115 B), added to
 * the button so the size shown is what the tap really downloads. Re-measure on a library bump.
 */
const LAZY_JS_BYTES = 1_163_115;

/** The family's file size is not in the API: the largest library file bounds a draft scene. */
const OWN_SCENE_MEGABYTES = Math.ceil(
  (Math.max(...Object.values(FILES).map((f) => f.spzBytes)) + LAZY_JS_BYTES) / 1_000_000,
);

export type World3dAssets = {
  spzUrl: string;
  /** Opened quietly when `spzUrl` fails to load. */
  fallbackSpzUrl?: string;
  panoUrl: string;
  thumbUrl: string;
  megabytes: number;
  /** True when the size is a ceiling, not the file's own: the family's scene is not measured. */
  sizeIsCeiling: boolean;
};

export function worldForGenre(genre: string): World3dAssets | null {
  const id = Object.hasOwn(GENRE_WORLD, genre) ? GENRE_WORLD[genre] : undefined;
  if (!id) return null;
  const f = FILES[id];
  const base = `/worlds/${id}`;
  return {
    spzUrl: `${base}/${f.spz}`,
    panoUrl: `${base}/${f.pano}`,
    thumbUrl: `${base}/${f.thumb}`,
    megabytes: Math.ceil((f.spzBytes + LAZY_JS_BYTES) / 1_000_000),
    sizeIsCeiling: false,
  };
}

/** The family's ready scene when there is one, else the library world of the genre. */
export function worldForScene(
  genre: string,
  own?: { spzUrl: string; panoUrl: string },
): World3dAssets | null {
  const library = worldForGenre(genre);
  if (!own) return library;
  return {
    spzUrl: own.spzUrl,
    fallbackSpzUrl: library?.spzUrl,
    panoUrl: own.panoUrl,
    thumbUrl: own.panoUrl,
    megabytes: OWN_SCENE_MEGABYTES,
    sizeIsCeiling: true,
  };
}
