import type { PerspectiveCamera, Scene, WebGLRenderer } from "three";
import { bindControls } from "@/lib/world-3d-controls";
import type { World3dAssets } from "@/lib/world-3d-assets";
import {
  aimWithGrace,
  cameraFitter,
  fovForAspect,
  panoramaScores,
  pixelRatioGovernor,
  startView,
} from "@/lib/world-3d-view";

const INIT_TIMEOUT_MS = 20_000;
/** 1.5 left DPR-3 phones visibly soft; 2 costs ~1.8x the fill of 1.5, still far below native 3. */
const MAX_PIXEL_RATIO = 2;
/** Splat centres looked at to find free space around the camera; a stride over the file, not all of it. */
const MAX_SAMPLED_SPLATS = 50_000;

export type Viewer = { dispose: () => void };

type Session = {
  renderer: WebGLRenderer;
  scene: Scene;
  camera: PerspectiveCamera;
  /** Frame time in, a lower pixel ratio out once when the device cannot keep up. */
  slow: (frameMs: number) => number | null;
};
type SparkModule = typeof import("@sparkjsdev/spark");

// One renderer per page session: Spark leaks ~200 MB of WASM per fresh scene (issue #401).
let session: Promise<Session> | null = null;

async function createSession(): Promise<Session> {
  const [three, spark] = await Promise.all([import("three"), import("@sparkjsdev/spark")]);
  // Throws when WebGL2 is unavailable: no separate probe context.
  const renderer = new three.WebGLRenderer({
    antialias: false,
    powerPreference: "high-performance",
  });
  const ratio = Math.min(window.devicePixelRatio, MAX_PIXEL_RATIO);
  renderer.setPixelRatio(ratio);
  const scene = new three.Scene();
  scene.add(new spark.SparkRenderer({ renderer }));
  return {
    renderer,
    scene,
    camera: new three.PerspectiveCamera(fovForAspect(1), 1, 0.01, 1000),
    slow: pixelRatioGovernor(ratio),
  };
}

// A context taken while no viewer was open (iOS under memory pressure) is not heard: check here.
function getSession(): Promise<Session> {
  session ??= createSession().catch((e: unknown) => {
    session = null;
    throw e;
  });
  const mine = session;
  return mine.then((s) => {
    if (!s.renderer.getContext().isContextLost()) return s;
    s.renderer.dispose();
    if (session === mine) session = null; // a concurrent open may already have replaced it
    return getSession();
  });
}

// Newest startViewer owns the shared canvas and loop; an older one must not touch them.
let latest = 0;

/** The file itself could not be fetched: the only failure worth a second file. */
class FileLoadError extends Error {}

async function loadMesh(spark: SparkModule, url: string, signal: AbortSignal) {
  const res = await fetch(url, { signal }).catch((e: unknown) => {
    throw signal.aborted ? e : new FileLoadError("world file unreachable", { cause: e });
  });
  if (!res.ok) throw new FileLoadError(`world file ${res.status}`);
  const mesh = new spark.SplatMesh({
    fileBytes: new Uint8Array(await res.arrayBuffer()),
    fileType: spark.SplatFileType.SPZ,
  });
  mesh.quaternion.set(1, 0, 0, 0); // Marble exports are Y-down
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error("world init timeout")), INIT_TIMEOUT_MS);
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
  try {
    await Promise.race([mesh.initialized, timeout]);
  } catch (e) {
    mesh.dispose();
    throw e;
  } finally {
    clearTimeout(timer);
  }
  return mesh;
}

/** Flat xyz centres of at most `MAX_SAMPLED_SPLATS` splats, in world space (the mesh is turned upright). */
function splatCentres(mesh: InstanceType<SparkModule["SplatMesh"]>): Float32Array {
  const packed = mesh.packedSplats;
  const total = packed?.numSplats ?? 0;
  const stride = Math.max(1, Math.ceil(total / MAX_SAMPLED_SPLATS));
  const centres = new Float32Array(3 * Math.ceil(total / stride));
  for (let i = 0, n = 0; packed && i < total; i += stride, n += 3) {
    const { x, y, z } = packed.getSplat(i).center.applyQuaternion(mesh.quaternion);
    centres.set([x, y, z], n);
  }
  return centres;
}

/**
 * Show the world inside `host`. Rejects when it cannot (no WebGL2, 404, network, init timeout);
 * `onLost` fires once if the GL context is taken away later. Caller shows the panorama then.
 * Aborting `signal` cancels the download and the init timer; a newer call supersedes this one.
 */
export async function startViewer(
  host: HTMLElement,
  world: Pick<World3dAssets, "spzUrl" | "fallbackSpzUrl" | "panoUrl">,
  onLost: () => void,
  signal: AbortSignal,
): Promise<Viewer> {
  const aim = aimWithGrace((reading) => panoramaScores(world.panoUrl, reading), signal, []);
  try {
    return await show(host, { spzUrl: world.spzUrl, aim }, onLost, signal);
  } catch (e) {
    if (!world.fallbackSpzUrl || signal.aborted || !(e instanceof FileLoadError)) throw e;
    console.warn("own world failed to load, showing the library one", e);
    // The library file is another world: the family's panorama does not aim it.
    return await show(host, { spzUrl: world.fallbackSpzUrl, aim: async () => [] }, onLost, signal);
  } finally {
    aim.stop(); // a no-op once aimed; ends the read of a walk that failed before its aim
  }
}

/** Renders each frame; the pixel-ratio governor is not fed the first frame after the page was hidden or shown. */
function runLoop({ renderer, scene, camera, slow }: Session): () => void {
  let last: number | undefined;
  const away = () => {
    last = undefined;
  };
  document.addEventListener("visibilitychange", away);
  renderer.setAnimationLoop((time: number) => {
    const lower = last === undefined ? null : slow(time - last);
    last = time;
    if (lower) renderer.setPixelRatio(lower); // three re-applies the size itself
    renderer.render(scene, camera);
  });
  return () => document.removeEventListener("visibilitychange", away);
}

async function show(
  host: HTMLElement,
  { spzUrl, aim }: { spzUrl: string; aim: () => Promise<number[]> },
  onLost: () => void,
  signal: AbortSignal,
): Promise<Viewer> {
  const mine = ++latest;
  const current = await getSession();
  const { renderer, scene, camera } = current;
  signal.throwIfAborted();
  const mesh = await loadMesh(await import("@sparkjsdev/spark"), spzUrl, signal);
  const scores = await aim();
  if (signal.aborted || mine !== latest) {
    mesh.dispose();
    throw signal.reason ?? new Error("superseded by a newer viewer");
  }
  const { yaw: initialYaw, back } = startView(scores, splatCentres(mesh));
  camera.position.set(Math.sin(initialYaw) * back, 0, Math.cos(initialYaw) * back); // behind the aim
  const canvas = renderer.domElement;
  const unbind = bindControls(canvas, camera, initialYaw);
  const fit = cameraFitter(camera);
  const resize = () => {
    const w = host.clientWidth || window.innerWidth;
    const h = host.clientHeight || window.innerHeight;
    renderer.setSize(w, h);
    fit(w, h);
  };
  let stopLoop = () => {};
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    unbind();
    stopLoop();
    window.removeEventListener("resize", resize);
    canvas.removeEventListener("webglcontextlost", lost);
    scene.remove(mesh);
    mesh.dispose();
    if (mine !== latest) return;
    renderer.setAnimationLoop(null);
    canvas.remove();
  };
  function lost(e: Event) {
    e.preventDefault();
    dispose();
    session = null;
    renderer.dispose();
    onLost();
  }
  canvas.addEventListener("webglcontextlost", lost);
  window.addEventListener("resize", resize);
  host.append(canvas);
  canvas.dataset.initialYaw = String(initialYaw); // read by the e2e that checks where the walk opens
  canvas.dataset.initialBack = String(back);
  canvas.style.cssText = "display:block;width:100%;height:100%";
  resize();
  scene.add(mesh);
  stopLoop = runLoop(current);
  return { dispose };
}
