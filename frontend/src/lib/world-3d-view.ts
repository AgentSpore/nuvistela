/** First view of a 3D world: wide on any screen and turned toward the liveliest part of it. */

const ACROSS_DEG = 80;
export const FOV_MIN = 25;
export const FOV_MAX = 100;
const OPEN_FOV_MIN = 60;
/** Rows of the panorama searched for the subject: the horizon, ±27°. */
const BAND = [0.35, 0.65] as const;
/** Panorama columns scored together: roughly what the first frame shows across. */
const WINDOW = ACROSS_DEG / 360;
const SAMPLE_WIDTH = 256;
/** Yaw sectors the horizon is cut into when looking for free space. */
const SECTORS = 64;
/** Splats from 20° above to 5° below the horizon (sine of the pitch): what blocks the walk. The floor further down is not a wall. */
const DEPTH_BAND = [-Math.sin((5 * Math.PI) / 180), Math.sin((20 * Math.PI) / 180)] as const;
/** A sector with fewer horizon splats than this is open sky, not content. */
const MIN_SECTOR_SPLATS = 20;
/** Nearest content = this quantile of a sector's distances, so a few stray splats do not block it. */
const NEAR_QUANTILE = 0.1;
/**
 * A sector is blocked when its nearest content lies within this share of the world's far
 * horizon distance (`FAR_QUANTILE`). Relative, not metres: Marble worlds come in any scale (the
 * library sky islands and lighthouse have a horizon at ~1 unit, the nook at ~6). The far
 * distance, not the median: in a dense forest the median is itself a trunk's distance, so
 * nothing in it read as close.
 */
const NEAR_SHARE = 0.25;
const FAR_QUANTILE = 0.9;
/** Half-width (degrees) of the central half of the first frame: 15° on a 390×844 phone, 25° on a 1440×900 screen; the wider one. */
const CENTRE_DEG = 25;
/** The camera backs off in steps of this share of the far distance, at most `BACK_STEPS` times. */
const BACK_STEP = 0.05;
const BACK_STEPS = 10;
/** Nearest content in the central cone = this quantile, so a floating splat does not push the camera back. */
const CONE_QUANTILE = 0.05;
/** The camera never backs closer than this share of a blocked sector's limit to content behind it (it must stand somewhere, not look at it). */
const REAR_SHARE = 0.5;
/** Sectors either side of the aim (±17°) that must be free too. */
const CLEARANCE = 3;
/** How long a ready world waits for its panorama's aim. */
const AIM_GRACE_MS = 500;
/** Below 30 fps over a 60-frame block the screen falls back from ratio 2 to 1.5. */
const SLOW_FRAME_MS = 33;
const SLOW_BLOCK_FRAMES = 60;
const SLOW_PIXEL_RATIO = 1.5;

const toRad = (deg: number) => (deg * Math.PI) / 180;

/** Vertical field of view (three.js `fov`) that shows ~80° across, so a portrait phone is not a close-up. */
export function fovForAspect(aspect: number): number {
  const vertical = (2 * Math.atan(Math.tan(toRad(ACROSS_DEG) / 2) / aspect) * 180) / Math.PI;
  return Math.min(FOV_MAX, Math.max(OPEN_FOV_MIN, vertical));
}

type Pixels = { data: Uint8ClampedArray; width: number; height: number };

function columnScores({ data, width, height }: Pixels): number[] {
  const scores = new Array<number>(width).fill(0);
  const at = (i: number) => data[i] ?? 0;
  const luma = (i: number) => 0.3 * at(i) + 0.59 * at(i + 1) + 0.11 * at(i + 2);
  for (let y = Math.floor(height * BAND[0]); y < Math.ceil(height * BAND[1]); y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const rgb = [at(i), at(i + 1), at(i + 2)];
      const chroma = (Math.max(...rgb) - Math.min(...rgb)) / 255;
      const detail = Math.abs(luma(i) - luma((y * width + ((x + 1) % width)) * 4)) / 255;
      scores[x] = (scores[x] ?? 0) + chroma * detail;
    }
  }
  return scores;
}

/** Index of the best `2 * half`-column window centre; -1 when no column scores at all. */
function bestWindow(scores: number[], half: number, centreOk: (c: number) => boolean): number {
  const width = scores.length;
  const windowAt = (c: number) => {
    let sum = 0;
    for (let d = -half; d < half; d++) sum += scores[(c + d + width) % width] ?? 0;
    return sum;
  };
  let best = -1;
  let bestScore = 0;
  for (let c = 0; c < width; c++) {
    if (!centreOk(c)) continue;
    const s = windowAt(c);
    if (s > bestScore * 1.0001) [best, bestScore] = [c, s];
  }
  return best;
}

/**
 * Camera yaw (radians, three.js Y rotation) facing the middle of the most colourful, detailed
 * stretch of the horizon in an equirectangular panorama: the best window, then the
 * score-weighted centre inside it, so the subject sits mid-frame rather than at the window's
 * edge. The panorama centre is straight ahead (yaw 0); columns grow to the right.
 */
export function vividYaw(pixels: Pixels): number {
  return yawOfScores(columnScores(pixels));
}

function yawOfScores(scores: number[]): number {
  return windowYaw(scores, () => true) ?? 0;
}

/** Yaw of the best window whose centre passes `centreOk`; null when there is none. */
function windowYaw(scores: number[], centreOk: (c: number) => boolean): number | null {
  const width = scores.length;
  const half = Math.max(1, Math.round((width * WINDOW) / 2));
  const best = bestWindow(scores, half, centreOk);
  if (best < 0) return null;
  let mass = 0;
  let moment = 0;
  for (let d = -half; d < half; d++) {
    const s = scores[(best + d + width) % width] ?? 0;
    mass += s;
    moment += s * d;
  }
  // +0.5: a column's score sits at its pixel centre.
  const u = (best + moment / mass + 0.5) / width;
  const yaw = (0.5 - u) * 2 * Math.PI;
  return Math.atan2(Math.sin(yaw), Math.cos(yaw));
}

async function readScores(url: string, signal: AbortSignal): Promise<number[]> {
  const blob = await (await fetch(url, { signal })).blob();
  const bitmap = await createImageBitmap(blob, {
    resizeWidth: SAMPLE_WIDTH,
    resizeHeight: SAMPLE_WIDTH / 2,
  });
  signal.throwIfAborted();
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d");
  ctx?.drawImage(bitmap, 0, 0);
  bitmap.close();
  return ctx ? columnScores(ctx.getImageData(0, 0, canvas.width, canvas.height)) : [];
}

/** Vividness per column of the panorama at `url`; none when it cannot be read. Rejects only on `signal`. */
export async function panoramaScores(url: string, signal: AbortSignal): Promise<number[]> {
  try {
    return await readScores(url, signal);
  } catch (e) {
    if (signal.aborted) throw e;
    return []; // an unreadable panorama only costs the aim, never the walk
  }
}

const sectorYaw = (sector: number) => (0.5 - (sector + 0.5) / SECTORS) * 2 * Math.PI;
const sectorOfYaw = (yaw: number) =>
  Math.min(SECTORS - 1, Math.floor((0.5 - yaw / (2 * Math.PI)) * SECTORS));

const quantile = (sorted: number[], q: number) => sorted[Math.floor(q * (sorted.length - 1))];

/** Nearest horizon content per yaw sector (Infinity when open) and the far horizon distance. */
function sectorDepths(centres: ArrayLike<number>): { near: number[]; scale: number } {
  const bins: number[][] = Array.from({ length: SECTORS }, () => []);
  const all: number[] = [];
  for (let i = 0; i + 2 < centres.length; i += 3) {
    const x = centres[i] ?? 0;
    const y = centres[i + 1] ?? 0;
    const z = centres[i + 2] ?? 0;
    const d = Math.hypot(x, y, z);
    if (d === 0 || y / d < DEPTH_BAND[0] || y / d > DEPTH_BAND[1]) continue;
    bins[sectorOfYaw(Math.atan2(-x, -z))]?.push(d);
    all.push(d);
  }
  const near = bins.map((b) =>
    b.length < MIN_SECTOR_SPLATS
      ? Infinity
      : (quantile(
          b.sort((p, q) => p - q),
          NEAR_QUANTILE,
        ) ?? Infinity),
  );
  return {
    near,
    scale:
      quantile(
        all.sort((p, q) => p - q),
        FAR_QUANTILE,
      ) ?? 0,
  };
}

/** Whether sector `s` and `CLEARANCE` sectors either side are all free: the frame is wide, a close object off centre still fills its edge. */
const withinReach = (free: boolean[], s: number) =>
  Array.from(
    { length: 2 * CLEARANCE + 1 },
    (_, i) => free[(s + i - CLEARANCE + SECTORS) % SECTORS],
  ).every(Boolean);

/**
 * Where the first frame looks. `scores` (vividness per panorama column) picks the liveliest
 * stretch, but only among yaw sectors whose nearest content is not right in front of the
 * camera (`centres`: flat xyz splat centres in world space, camera at the origin). When every
 * sector is free it is simply the liveliest stretch. When no sector is free, or none that is
 * free is vivid, it faces the open sector with the most room (sectors too sparse to measure do
 * not count).
 */
export function startYaw(scores: number[], centres: ArrayLike<number>): number {
  return startView(scores, centres).yaw;
}

/**
 * `startYaw` plus how far the camera first steps back along the opposite of that aim (world
 * units; 0 when the middle of the frame is already clear). Needed when no direction is free,
 * as in a dense forest: the camera backs off until the nearest content in the central cone is
 * no closer than a blocked sector's limit, at most `BACK_STEPS` steps.
 */
export function startView(
  scores: number[],
  centres: ArrayLike<number>,
): { yaw: number; back: number } {
  const { near, scale } = sectorDepths(centres);
  const yaw = aimYaw(scores, near, scale);
  return { yaw, back: Number.isFinite(scale) && scale > 0 ? backOff(yaw, centres, scale) : 0 };
}

/** Distance the camera steps back so the central cone of the frame at `yaw` holds nothing closer than the blocked limit. */
function backOff(yaw: number, centres: ArrayLike<number>, scale: number): number {
  const limit = NEAR_SHARE * scale;
  let best = { back: 0, near: -1 };
  for (let k = 0; k <= BACK_STEPS; k++) {
    const back = k * BACK_STEP * scale;
    if (k > 0 && coneNearest(yaw, back, centres, -1) < REAR_SHARE * limit) break;
    const near = coneNearest(yaw, back, centres);
    if (near >= limit) return back;
    if (near > best.near) best = { back, near };
  }
  return best.back;
}

const inHorizonBand = (y: number, d: number) =>
  d > 0 && y / d >= DEPTH_BAND[0] && y / d <= DEPTH_BAND[1];

/** Whether the ground-plane vector (vx, vz) lies ahead of the camera within `CENTRE_DEG` of its facing (fx, fz). */
function inCone(vx: number, vz: number, fx: number, fz: number): boolean {
  const ahead = vx * fx + vz * fz;
  return ahead > 0 && Math.atan2(Math.abs(vx * fz - vz * fx), ahead) <= toRad(CENTRE_DEG);
}

/** Nearest horizon content inside the central cone (`facing` -1: the one behind) from the camera `back` behind the origin; Infinity when too sparse to tell. */
function coneNearest(
  yaw: number,
  back: number,
  centres: ArrayLike<number>,
  facing: 1 | -1 = 1,
): number {
  const [fx, fz] = [-Math.sin(yaw), -Math.cos(yaw)];
  const dists: number[] = [];
  for (let i = 0; i + 2 < centres.length; i += 3) {
    const vx = (centres[i] ?? 0) + fx * back;
    const vy = centres[i + 1] ?? 0;
    const vz = (centres[i + 2] ?? 0) + fz * back;
    const d = Math.hypot(vx, vy, vz);
    if (inHorizonBand(vy, d) && inCone(vx, vz, fx * facing, fz * facing)) dists.push(d);
  }
  if (dists.length < MIN_SECTOR_SPLATS) return Infinity;
  return (
    quantile(
      dists.sort((p, q) => p - q),
      CONE_QUANTILE,
    ) ?? Infinity
  );
}

/** Where the first frame looks, given the nearest content per sector; see `startYaw`. */
function aimYaw(scores: number[], near: number[], scale: number): number {
  const free = near.map((d) => d >= NEAR_SHARE * scale);
  if (free.every(Boolean)) return yawOfScores(scores);
  // A sparse sector reads Infinity: free for the vivid choice, but never "roomiest" (it may be a void).
  const roomiest = sectorYaw(near.indexOf(Math.max(...near.filter(Number.isFinite))));
  const sectorOf = (c: number) => Math.floor((c * SECTORS) / scores.length);
  const clear = free.map((_, s) => withinReach(free, s));
  const kept = scores.map((v, c) => (free[sectorOf(c)] ? v : 0));
  const yaw = windowYaw(kept, (c) => clear[sectorOf(c)] ?? false);
  if (yaw === null) return roomiest;
  const s = nearestClear(clear, sectorOfYaw(yaw));
  if (s < 0) return roomiest;
  return s === sectorOfYaw(yaw) ? yaw : sectorYaw(s);
}

/** Nearest clear sector to `s` (itself first, circularly); -1 when none. The vivid centroid can drift a little out of the run its window centre was in. */
function nearestClear(clear: boolean[], s: number): number {
  for (let k = 0; k <= SECTORS / 2; k++) {
    for (const t of [(s - k + SECTORS) % SECTORS, (s + k) % SECTORS]) if (clear[t]) return t;
  }
  return -1;
}

/**
 * Starts `read` now, alongside the world download. The returned call, made once the world is
 * ready, waits at most `AIM_GRACE_MS` more for it, then stops the read and opens straight ahead.
 * Aborting `signal`, or calling `stop` on the returned call, stops the read too. Composed by hand: Safari before 17.4 has no AbortSignal.any.
 */
export function aimWithGrace<T>(
  read: (signal: AbortSignal) => Promise<T>,
  signal: AbortSignal,
  fallback: T,
): (() => Promise<T>) & { stop: () => void } {
  const reading = new AbortController();
  const stop = () => {
    reading.abort();
    signal.removeEventListener("abort", stop);
  };
  if (signal.aborted) reading.abort();
  else signal.addEventListener("abort", stop, { once: true });
  const aimed = read(reading.signal).catch(() => fallback);
  const aim = async () => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const late = new Promise<T>((resolve) => {
      timer = setTimeout(() => resolve(fallback), AIM_GRACE_MS);
    });
    try {
      return await Promise.race([aimed, late]);
    } finally {
      clearTimeout(timer);
      stop();
    }
  };
  return Object.assign(aim, { stop });
}

type FittedCamera = { fov: number; aspect: number; updateProjectionMatrix: () => void };

/** Sizes the camera to the screen; a pinch zoom survives as a share of the default view. */
export function cameraFitter(camera: FittedCamera): (width: number, height: number) => void {
  let base = 0;
  return (width, height) => {
    const zoom = base ? camera.fov / base : 1;
    camera.aspect = width / height;
    base = fovForAspect(camera.aspect);
    camera.fov = Math.min(FOV_MAX, Math.max(FOV_MIN, base * zoom));
    camera.updateProjectionMatrix();
  };
}

/**
 * Fed each frame time (ms), minus any time the page was away (the caller drops that frame); returns the lower pixel ratio once, when a full block of frames
 * after the warm-up block averages over the budget, else null. One step down, never back up.
 */
export function pixelRatioGovernor(ratio: number): (frameMs: number) => number | null {
  let frames = 0;
  let total = 0;
  let blocks = 0;
  let done = ratio <= SLOW_PIXEL_RATIO;
  return (frameMs) => {
    if (done) return null;
    total += frameMs;
    if (++frames < SLOW_BLOCK_FRAMES) return null;
    const slow = blocks++ > 0 && total / frames > SLOW_FRAME_MS;
    [frames, total] = [0, 0];
    if (!slow) return null;
    done = true;
    return SLOW_PIXEL_RATIO;
  };
}
