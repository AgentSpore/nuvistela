import { afterEach, expect, it, onTestFinished, vi } from "vitest";
import {
  cameraFitter,
  fovForAspect,
  aimWithGrace,
  panoramaScores,
  pixelRatioGovernor,
  startView,
  startYaw,
  vividYaw,
} from "@/lib/world-3d-view";

const W = 64;
const H = 32;

/** Flat grey equirect with a busy colourful stretch of `columns` (wrapping past W) in `rows`. */
function pano(columns: [number, number], rows: [number, number]) {
  const data = new Uint8ClampedArray(W * H * 4).fill(120);
  for (let y = rows[0]; y < rows[1]; y++) {
    for (let c = columns[0]; c < columns[1]; c++) {
      const x = c % W;
      const i = (y * W + x) * 4;
      const on = (x + y) % 2 === 0;
      data.set(on ? [250, 140, 20] : [40, 90, 200], i);
    }
  }
  return { data, width: W, height: H };
}

/** Signed distance in columns between the view direction and `x`, across the wrap seam. */
const offCentre = (yaw: number, x: number) => {
  const d = (0.5 - yaw / (2 * Math.PI)) * W - x;
  return ((((d + W / 2) % W) + W) % W) - W / 2;
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it.each([
  ["right of centre", [46, 52], 49],
  ["left of centre", [8, 12], 10],
  ["across the wrap seam", [62, 67], 0.5],
] as const)("faces the middle of a colourful stretch %s, within a column", (_, cols, centre) => {
  expect(
    Math.abs(offCentre(vividYaw(pano([cols[0], cols[1]], [12, 20])), centre)),
  ).toBeLessThanOrEqual(1);
});

it("ignores colour above and below the horizon band, and looks ahead when nothing stands out", () => {
  expect(vividYaw(pano([46, 52], [0, 4]))).toBe(0);
  expect(vividYaw(pano([0, 0], [0, 0]))).toBe(0);
});

it("keeps about 80 degrees across on any screen, within the zoom limits", () => {
  const across = (aspect: number) =>
    (2 * Math.atan(Math.tan((fovForAspect(aspect) * Math.PI) / 360) * aspect) * 180) / Math.PI;
  expect(across(1.2)).toBeCloseTo(80, 0);
  expect(fovForAspect(390 / 844)).toBe(100);
  expect(across(390 / 844)).toBeGreaterThan(55);
  expect(fovForAspect(3)).toBe(60);
});

it("reads the aim without AbortSignal.any (Safari before 17.4)", async () => {
  const any = AbortSignal.any;
  Object.assign(AbortSignal, { any: undefined });
  onTestFinished(() => void Object.assign(AbortSignal, { any }));
  const fetch = vi.fn(async () => new Response(new Blob([new Uint8Array(4)])));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("createImageBitmap", async () => ({
    width: W,
    height: H,
    close: vi.fn(),
  }));
  vi.stubGlobal(
    "OffscreenCanvas",
    class {
      constructor(
        readonly width: number,
        readonly height: number,
      ) {}
      getContext = () => ({
        drawImage: vi.fn(),
        getImageData: () => pano([46, 52], [12, 20]),
      });
    },
  );
  const scores = await panoramaScores("/p.webp", new AbortController().signal);
  expect(fetch).toHaveBeenCalled();
  expect(Math.abs(offCentre(startYaw(scores, []), 49))).toBeLessThanOrEqual(1);
});

/** A panorama read that answers `value` after `ms`, or fails as soon as it is stopped. */
const later = (ms: number, value: number, signal: AbortSignal) =>
  new Promise<number>((resolve, reject) => {
    setTimeout(() => resolve(value), ms);
    signal.addEventListener("abort", () => reject(signal.reason));
  });

it("uses a panorama that arrives before the world, however slow the link", async () => {
  vi.useFakeTimers();
  const aim = aimWithGrace((signal) => later(4000, 1.2, signal), new AbortController().signal, 0);
  await vi.advanceTimersByTimeAsync(5000); // the world file is ready only now
  await expect(aim()).resolves.toBe(1.2);
});

it("waits only a moment past the world for a stalled panorama, then stops reading it", async () => {
  vi.useFakeTimers();
  let reading: AbortSignal | undefined;
  const aim = aimWithGrace(
    (signal) => {
      reading = signal;
      return new Promise<number>(() => undefined);
    },
    new AbortController().signal,
    0,
  );
  await vi.advanceTimersByTimeAsync(5000);
  const yaw = aim();
  await vi.advanceTimersByTimeAsync(500);
  await expect(yaw).resolves.toBe(0);
  expect(reading?.aborted).toBe(true);
});

it("stops reading the panorama when the walk is closed", () => {
  const walk = new AbortController();
  let reading: AbortSignal | undefined;
  aimWithGrace(
    (signal) => {
      reading = signal;
      return new Promise<number>(() => undefined);
    },
    walk.signal,
    0,
  );
  walk.abort();
  expect(reading?.aborted).toBe(true);
});

it("keeps the user's zoom as a share of the default view when the screen turns", () => {
  const camera = { fov: 0, aspect: 1, updateProjectionMatrix: vi.fn() };
  const fit = cameraFitter(camera);
  fit(390, 844);
  expect(camera.fov).toBe(fovForAspect(390 / 844));
  camera.fov /= 2;
  fit(844, 390);
  expect(camera.fov).toBeCloseTo(fovForAspect(844 / 390) / 2);
});

it("drops a slow screen from ratio 2 to 1.5 once, after the warm-up, and never back", () => {
  const slow = pixelRatioGovernor(2);
  const feed = (ms: number, n: number) =>
    Array.from({ length: n }, () => slow(ms)).filter((r) => r !== null);
  expect(feed(80, 60)).toEqual([]); // warm-up: shader compile and first sort
  expect(feed(40, 60)).toEqual([1.5]);
  expect(feed(40, 600)).toEqual([]);
  expect(feed(10, 600)).toEqual([]);
});

it("steps a very slow screen down too: 300 ms frames are slow, not time away", () => {
  const slow = pixelRatioGovernor(2);
  const fed = Array.from({ length: 120 }, () => slow(300));
  expect(fed.filter((r) => r !== null)).toEqual([1.5]);
});

it("stops reading the panorama at once when the walk is already closed", () => {
  const walk = new AbortController();
  walk.abort();
  let reading: AbortSignal | undefined;
  aimWithGrace(
    (signal) => {
      reading = signal;
      return new Promise<number>(() => undefined);
    },
    walk.signal,
    0,
  );
  expect(reading?.aborted).toBe(true);
});

it("stop() ends the panorama read of a walk that never reached its aim", () => {
  let reading: AbortSignal | undefined;
  const aim = aimWithGrace(
    (signal) => {
      reading = signal;
      return new Promise<number>(() => undefined);
    },
    new AbortController().signal,
    0,
  );
  aim.stop();
  expect(reading?.aborted).toBe(true);
});

it("leaves a fast screen, and one already at 1.5, alone", () => {
  const fast = pixelRatioGovernor(2);
  expect(Array.from({ length: 600 }, () => fast(20)).filter((r) => r !== null)).toEqual([]);
  const low = pixelRatioGovernor(1.5);
  expect(Array.from({ length: 600 }, () => low(50)).filter((r) => r !== null)).toEqual([]);
});

/** Flat xyz centres on the horizon: `[yaw, distance]` pairs, three.js yaw (0 ahead, left positive). */
const ring = (points: [number, number][]) =>
  Float32Array.from(points.flatMap(([yaw, d]) => [-d * Math.sin(yaw), 0, -d * Math.cos(yaw)]));

/** Every sector (5.6 degrees) gets 20 points at `far`; `blob` adds `n` points at `d` over columns `cols`. */
const sweep = (far: number, blob?: { cols: [number, number]; d: number; n: number }) => {
  const pts: [number, number][] = [];
  for (let k = 0; k < 64; k++) for (let i = 0; i < 20; i++) pts.push([yawOfColumn(k), far]);
  for (let c = blob?.cols[0] ?? 0; c < (blob?.cols[1] ?? 0); c++)
    for (let i = 0; i < (blob?.n ?? 0); i++) pts.push([yawOfColumn(c), blob?.d ?? 0]);
  return ring(pts);
};

/** Panorama column scores (64 columns) with one hump at `column`. */
const hump = (column: number) =>
  Array.from({ length: W }, (_, c) => Math.max(0, 5 - Math.abs(offCentreColumn(c, column))));
const offCentreColumn = (c: number, centre: number) =>
  ((((c - centre + W / 2) % W) + W) % W) - W / 2;
const yawOfColumn = (c: number) => (0.5 - (c + 0.5) / W) * 2 * Math.PI;
const apart = (a: number, b: number) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)));

it("turns away from a close object in the vivid direction and faces the next vivid stretch", () => {
  const vivid = hump(10);
  const blob = { cols: [4, 17] as [number, number], d: 0.3, n: 30 };
  const second = vivid.map((v, c) => v + Math.max(0, 3 - Math.abs(offCentreColumn(c, 40))));
  const yaw = startYaw(second, sweep(10, blob));
  expect(apart(yaw, yawOfColumn(10))).toBeGreaterThan(1);
  expect(apart(yaw, yawOfColumn(40))).toBeLessThan(0.3);
});

it("keeps the vivid direction when nothing is close", () => {
  expect(apart(startYaw(hump(10), sweep(10)), yawOfColumn(10))).toBeLessThan(0.2);
});

it("faces the farthest side when every direction has something close", () => {
  const pts: [number, number][] = [];
  for (let k = 0; k < 64; k++) {
    const yaw = ((k + 0.5) / 64) * 2 * Math.PI;
    for (let i = 0; i < 100; i++) pts.push([yaw, i < 20 ? (k === 30 ? 2 : 0.5) : 10]);
  }
  const yaw = startYaw(hump(10), ring(pts));
  expect(apart(yaw, (30.5 / 64) * 2 * Math.PI)).toBeLessThan(0.2);
});

it("keeps a vivid stretch whose centroid drifts out of the clear run, at the run's edge", () => {
  const pts: [number, number][] = [];
  for (let k = 0; k < 64; k++)
    for (let i = 0; i < 40; i++) pts.push([yawOfColumn(k), k <= 20 || i >= 12 ? 10 : 0.5]);
  const scores = Array.from({ length: W }, (_, c) => (c >= 17 && c <= 20 ? 5 : 0));
  expect(apart(startYaw(scores, ring(pts)), yawOfColumn(17))).toBeLessThan(0.01);
});

it("never faces a sector too sparse to tell open from void when others hold content", () => {
  const pts: [number, number][] = [];
  for (let k = 0; k < 64; k++) {
    if (k >= 40 && k <= 45) for (let i = 0; i < 5; i++) pts.push([yawOfColumn(k), 10]);
    else
      for (let i = 0; i < 40; i++) pts.push([yawOfColumn(k), i < 12 ? (k === 30 ? 2 : 0.5) : 10]);
  }
  expect(apart(startYaw(hump(10), ring(pts)), yawOfColumn(30))).toBeLessThan(0.1);
});

it("ignores floor splats below eye level when judging what is close", () => {
  const flat: number[] = [];
  for (let k = 0; k < 64; k++)
    for (let i = 0; i < 40; i++) {
      const [d, pitch] = i < 15 ? [2.9, (-19 * Math.PI) / 180] : [10, 0];
      const yaw = yawOfColumn(k);
      flat.push(
        -d * Math.cos(pitch) * Math.sin(yaw),
        d * Math.sin(pitch),
        -d * Math.cos(pitch) * Math.cos(yaw),
      );
    }
  expect(apart(startYaw(hump(10), Float32Array.from(flat)), yawOfColumn(10))).toBeLessThan(0.2);
});

/** Ring where `free` sectors hold far content and the rest 30% close clutter; `extra` overrides a sector's far distance. */
const clutter = (free: (k: number) => boolean, extra: Record<number, number> = {}) => {
  const pts: [number, number][] = [];
  for (let k = 0; k < 64; k++)
    for (let i = 0; i < 40; i++)
      pts.push([yawOfColumn(k), free(k) || i >= 12 ? (extra[k] ?? 10) : 0.5]);
  return ring(pts);
};
const vividAt = (cols: number[]) => Array.from({ length: W }, (_, c) => (cols.includes(c) ? 5 : 0));

it("faces the roomiest sector when no vivid window fits in a clear run", () => {
  const centres = clutter((k) => k <= 10 || k === 40, { 40: 20 });
  expect(apart(startYaw(vividAt([40]), centres), yawOfColumn(40))).toBeLessThan(0.01);
});

it("snaps a drifted vivid centre to the nearest clear sector on its right", () => {
  const centres = clutter((k) => (k >= 17 && k <= 37) || k === 50, { 50: 20 });
  expect(apart(startYaw(vividAt([17, 18, 19, 20]), centres), yawOfColumn(20))).toBeLessThan(0.01);
});

it("snaps across the 63/0 seam to a clear sector", () => {
  const centres = clutter((k) => k >= 61 || k <= 3 || k === 40, { 40: 20 });
  expect(apart(startYaw(vividAt([61, 62, 63]), centres), yawOfColumn(0))).toBeLessThan(0.01);
});

it("snaps leftwards across the 0/63 seam to a clear sector", () => {
  const centres = clutter((k) => k >= 60 || k <= 2 || k === 40, { 40: 20 });
  expect(apart(startYaw(vividAt([0, 1, 2]), centres), yawOfColumn(63))).toBeLessThan(0.01);
});

/** Dense forest ring: per sector 30% trunks at `trunk`, 45% at `mid`, 25% haze at 8 (a far backdrop keeps the world's scale large). */
const forest = (trunk: (k: number) => number, mid: (k: number) => number = () => 1.2) => {
  const pts: [number, number][] = [];
  for (let k = 0; k < 64; k++)
    for (let i = 0; i < 40; i++)
      pts.push([yawOfColumn(k), i < 12 ? trunk(k) : i < 30 ? mid(k) : 8]);
  return ring(pts);
};

it("turns from a trunk 0.6 away in a forest whose own median is small, to the open side", () => {
  const centres = forest(
    (k) => (k < 18 || k >= 32 ? 0.6 : k === 25 ? 3 : 2.5),
    (k) => (k < 18 || k >= 32 ? 1.2 : k === 25 ? 3 : 2.5),
  );
  const { yaw, back } = startView(hump(10), centres);
  expect(apart(yaw, yawOfColumn(25))).toBeLessThan(0.2);
  expect(back).toBe(0);
});

/** Aim at sector 10 (roomiest by its own p10), trunks 0.8 on its flanks, `rear` distance behind, 2.4 elsewhere. */
const crowdedFront = (rear: number, front = 0.8) =>
  forest(
    (k) => (k === 10 ? 4 : Math.abs(k - 10) <= 5 ? front : Math.abs(k - 42) <= 6 ? rear : 2.4),
    (k) => (k === 10 ? 4 : Math.abs(k - 10) <= 5 ? front : Math.abs(k - 42) <= 6 ? rear : 2.4),
  );

it("steps back along the aim until the middle of the frame is clear", () => {
  const { back } = startView(hump(10), crowdedFront(2.4));
  expect(back).toBeGreaterThanOrEqual(1.2);
  expect(back).toBeLessThanOrEqual(4);
});

it("steps back as far as five steps when the content in front is almost on the camera", () => {
  expect(startView(hump(10), crowdedFront(3.5, 0.2)).back).toBeCloseTo(2, 5);
});

it("stops stepping back before it would stand against content behind it", () => {
  const { back } = startView(hump(10), crowdedFront(1.8));
  expect(back).toBeGreaterThan(0);
  expect(1.8 - back).toBeGreaterThanOrEqual(1); // half the 2.0 limit still free behind
});

it("does not step back in an open world", () => {
  expect(startView(hump(10), sweep(10)).back).toBe(0);
  expect(startView(hump(10), []).back).toBe(0);
});

it("never returns a non-finite step back when splat centres are infinite", () => {
  const far = Array.from({ length: 600 }, (_, i) => [0, 0, i % 2 ? -Infinity : Infinity]).flat();
  const { yaw, back } = startView(hump(10), Float32Array.from([...sweep(10), ...far]));
  expect(Number.isFinite(back)).toBe(true);
  expect(Number.isFinite(yaw)).toBe(true);
});
