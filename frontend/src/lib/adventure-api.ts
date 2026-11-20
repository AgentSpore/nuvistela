import { z } from "zod";
import { request } from "@/lib/api";

export const CHAPTER_STATUSES = [
  "queued",
  "writing",
  "ready",
  "delayed_model",
  "delayed_budget",
] as const;

const questSchema = z.object({
  id: z.string(),
  seq: z.number(),
  title: z.string(),
  description: z.string(),
  skill: z.string(),
  source: z.enum(["template", "model", "world"]),
  status: z.enum(["open", "done"]),
  reaction: z.string().nullish(),
});
const chapterSchema = z.object({
  id: z.string(),
  seq: z.number(),
  status: z.enum(CHAPTER_STATUSES),
  title: z.string().nullable(),
  body: z.string().nullable(),
});
const chapterRefSchema = chapterSchema.pick({ id: true, status: true });
export const WRITE_TIMEOUT_MS = 15_000; // start, done, retry: give up as a network error

const send = <S extends z.ZodType>(path: string, schema: S, init: RequestInit) =>
  request(path, schema, init, WRITE_TIMEOUT_MS);

export const GENRES = ["fairy_tale", "space", "pirates", "custom"] as const;
export type Genre = (typeof GENRES)[number];

const worldStatus = z.enum(["pending", "ready", "fallback"]);
const startedSchema = z.object({
  world_status: worldStatus.nullable(),
  quest: questSchema.nullable(),
});
const doneSchema = z.object({ chapter: chapterRefSchema });
const chronicleEntrySchema = z.object({ chapter: z.number(), text: z.string() });
export const adventureSchema = z.object({
  world: z.object({ status: worldStatus }).nullable(),
  quest: questSchema.nullable(),
  chapters: z.array(chapterSchema),
  // Absent (older backend) or unreadable counts as nothing to show.
  chronicle: z.array(chronicleEntrySchema).catch([]).optional(),
  skills: z.array(z.string()).catch([]).optional(),
});

const coverSchema = z.object({
  status: z.enum(["pending", "ready", "failed"]),
  // Only our own media route: anything else (another origin, odd path) is no cover at all.
  url: z
    .string()
    .regex(/^\/api\/v1\/media\/[0-9a-f]{64}\.webp$/)
    .nullable(),
  // Pending until the next UTC day (the daily budget is spent); absent on older servers.
  deferred: z.boolean().catch(false).optional(),
});

// The family's own 3D scene. Ready needs both files on our media route; pending is kept so the
// screen can re-fetch quietly. Failed, absent and anything odd are "no scene": the library world shows.
const sceneSchema = z.union([
  z.object({
    status: z.literal("ready"),
    url: z.string().regex(/^\/api\/v1\/media\/[0-9a-f]{64}\.spz$/),
    panorama_url: z.string().regex(/^\/api\/v1\/media\/pano\/[0-9a-f]{64}\.webp$/),
  }),
  z.object({ status: z.literal("pending") }),
]);

export const worldSchema = z.object({
  status: worldStatus,
  genre: z.string().catch("custom"),
  // Absent (older backend) or unreadable counts as no picture.
  cover: coverSchema.nullable().catch(null),
  // A new cover of this world is being made while the old one still shows; absent counts as no.
  cover_growing: z.boolean().catch(false).optional(),
  scene: sceneSchema.nullable().catch(null).optional(),
  world: z
    .object({
      title: z.string(),
      setting: z.string(),
      prologue: z.string(),
      locations: z.array(z.object({ name: z.string(), description: z.string() })),
      heroes: z.array(
        z.object({
          member_id: z.string(),
          hero_class: z.string(),
          trait: z.string(),
          skill: z.string(),
        }),
      ),
    })
    .nullable(),
});

export type WorldStatus = z.infer<typeof worldStatus>;
export type WorldView = NonNullable<z.infer<typeof worldSchema>["world"]>;
export type WorldResponse = z.infer<typeof worldSchema>;
export type Cover = NonNullable<WorldResponse["cover"]>;
export type SceneView = NonNullable<WorldResponse["scene"]>;
export type Scene = Extract<SceneView, { status: "ready" }>;
export type Quest = z.infer<typeof questSchema>;
export type Chapter = z.infer<typeof chapterSchema>;
export type ChapterStatus = Chapter["status"];
export type ChronicleEntry = z.infer<typeof chronicleEntrySchema>;
export type Adventure = z.infer<typeof adventureSchema>;

/** A chapter the backend is still working on: the screen polls while one exists. */
export const isPending = (c: Chapter): boolean =>
  c.status === "queued" || c.status === "writing";

/** A stalled read ends as a network error after this long, so the screen stops holding the quest back. */
export const WORLD_READ_TIMEOUT_MS = 8000;

/** `timeoutMs` is opt-in: without it the read waits as long as the server does. */
export const getAdventure = (familyId: string, timeoutMs?: number) =>
  request(`/families/${familyId}/adventure`, adventureSchema, undefined, timeoutMs);

export const getWorld = (familyId: string) =>
  request(`/families/${familyId}/world`, worldSchema, undefined, WORLD_READ_TIMEOUT_MS);

export const retryChapter = (chapterId: string) =>
  send(`/chapters/${chapterId}/retry`, chapterRefSchema, { method: "POST" });

export const startAdventure = (familyId: string, genre: Genre, customGenre?: string) =>
  send(`/families/${familyId}/adventure`, startedSchema, {
    method: "POST",
    body: JSON.stringify({ genre, custom_genre: customGenre }),
  });

export const markQuestDone = (questId: string, note: string, key: string) =>
  send(`/quests/${questId}/done`, doneSchema, {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({ note: note || undefined }),
  });

const keyName = (questId: string) => `idem:${questId}`;

/** One Idempotency-Key per quest: made on first use, reused by every retry until it succeeds. */
export function doneKey(questId: string): string {
  const name = keyName(questId);
  const key = sessionStorage.getItem(name) ?? crypto.randomUUID();
  sessionStorage.setItem(name, key);
  return key;
}

export const clearDoneKey = (questId: string) =>
  sessionStorage.removeItem(keyName(questId));
