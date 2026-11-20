import { afterEach, beforeEach, expect, it, vi } from "vitest";

const gl = vi.hoisted(() => ({
  ctor: vi.fn(),
  loop: vi.fn(),
  ratio: vi.fn(),
  rendererDispose: vi.fn(),
  lost: false,
  yaw: vi.fn(),
  view: undefined as undefined | (() => { yaw: number; back: number }),
  mesh: {
    dispose: vi.fn(),
    quaternion: { set: vi.fn() },
    initialized: Promise.resolve(),
    packedSplats: { numSplats: 0, getSplat: vi.fn() },
  },
  camera: {
    fov: 70,
    aspect: 1,
    rotation: { set: vi.fn() },
    position: { set: vi.fn() },
    updateProjectionMatrix: vi.fn(),
  },
}));

vi.mock("three", async (importActual) => {
  const { Vector3 } = await importActual<typeof import("three")>();
  class WebGLRenderer {
    domElement = document.createElement("canvas");
    constructor(opts: unknown) {
      gl.ctor(opts);
      if (!this.domElement.getContext("webgl2")) throw new Error("Error creating WebGL context.");
    }
    getContext = () => ({ isContextLost: () => gl.lost });
    setPixelRatio = gl.ratio;
    setSize = vi.fn();
    render = vi.fn();
    dispose = gl.rendererDispose;
    setAnimationLoop = gl.loop;
  }
  class Scene {
    add = vi.fn();
    remove = vi.fn();
  }
  class PerspectiveCamera {
    constructor() {
      return gl.camera;
    }
  }
  return { WebGLRenderer, Scene, PerspectiveCamera, Vector3 };
});
vi.mock("@sparkjsdev/spark", () => ({
  SparkRenderer: class {},
  SplatFileType: { SPZ: "spz" },
  SplatMesh: class {
    constructor() {
      return gl.mesh;
    }
  },
}));

vi.mock("@/lib/world-3d-view", async (actual) => {
  const real = await actual<typeof import("@/lib/world-3d-view")>();
  return {
    ...real,
    panoramaScores: gl.yaw,
    startView: (...args: Parameters<typeof real.startView>) =>
      gl.view?.() ?? real.startView(...args),
  };
});

/** Panorama column scores: one lively stretch, columns 9 to 11 of 64. */
const HUMP = Array.from({ length: 64 }, (_, c) => (c >= 9 && c <= 11 ? 1 : 0));
const yawOf = (column: number) => (0.5 - (column + 0.5) / 64) * 2 * Math.PI;
const WORLD = { spzUrl: "/worlds/x/w.spz", panoUrl: "/worlds/x/pano.webp" };
const ok = () => new Response(new Uint8Array([1, 2, 3]), { status: 200 });

async function begin(
  host: HTMLElement = document.createElement("div"),
  signal = new AbortController().signal,
) {
  const { startViewer } = await import("@/lib/world-3d-viewer");
  const onLost = vi.fn();
  return { host, onLost, promise: startViewer(host, WORLD, onLost, signal) };
}
const start = async (host?: HTMLElement) => (await begin(host)).promise;

beforeEach(() => {
  vi.resetModules();
  gl.lost = false;
  gl.view = undefined;
  gl.mesh.initialized = Promise.resolve();
  gl.camera.fov = 70;
  gl.yaw.mockResolvedValue([]);
  gl.mesh.packedSplats.numSplats = 0;
  Object.assign(gl.mesh, { quaternion: { set: vi.fn() } });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async () => ok()),
  );
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({}) as never;
  vi.stubGlobal("devicePixelRatio", 3);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

it("rejects without WebGL2 and never fetches the file", async () => {
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(null) as never;
  await expect((await begin()).promise).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();
});

it("rejects on a 404 and on a network error", async () => {
  vi.mocked(fetch).mockResolvedValueOnce(new Response("", { status: 404 }));
  await expect((await begin()).promise).rejects.toThrow();
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
  await expect((await begin()).promise).rejects.toThrow();
});

it("rejects when initialized does not settle within 20 s", async () => {
  vi.useFakeTimers();
  gl.mesh.initialized = new Promise(() => {});
  const { promise } = await begin();
  const settled = expect(promise).rejects.toThrow();
  await vi.advanceTimersByTimeAsync(20_001);
  await settled;
  expect(gl.mesh.dispose).toHaveBeenCalled();
});

it("aborting cancels the download and a pending init timer", async () => {
  vi.useFakeTimers();
  gl.mesh.initialized = new Promise(() => {});
  const abort = new AbortController();
  const { promise } = await begin(undefined, abort.signal);
  const settled = expect(promise).rejects.toThrow();
  await vi.advanceTimersByTimeAsync(10);
  expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({ signal: abort.signal });
  abort.abort();
  await settled;
  expect(vi.getTimerCount()).toBe(0);
  expect(gl.mesh.dispose).toHaveBeenCalled();
});

it("creates one renderer without antialias, caps the pixel ratio, disposes meshes", async () => {
  const host = document.createElement("div");
  (await start(host)).dispose();
  expect(gl.mesh.dispose).toHaveBeenCalledTimes(1);
  (await start(host)).dispose();
  expect(gl.ctor).toHaveBeenCalledTimes(1);
  expect(gl.ctor.mock.calls[0]?.[0]).toMatchObject({ antialias: false });
  expect(gl.ratio).toHaveBeenCalledWith(2);
});

it("dispose stops the loop, removes the canvas and the input listeners", async () => {
  const removed: string[] = [];
  const host = document.createElement("div");
  const viewer = await start(host);
  const canvas = host.querySelector("canvas") as HTMLCanvasElement;
  vi.spyOn(canvas, "removeEventListener").mockImplementation((t) => void removed.push(t));
  viewer.dispose();
  expect(gl.loop).toHaveBeenLastCalledWith(null);
  expect(host.querySelector("canvas")).toBeNull();
  expect(removed).toEqual(
    expect.arrayContaining(["pointerdown", "pointermove", "wheel", "webglcontextlost"]),
  );
});

it("an older viewer disposing late leaves the newest viewer's canvas and loop alone", async () => {
  const [host1, host2] = [document.createElement("div"), document.createElement("div")];
  const first = await start(host1);
  await start(host2);
  first.dispose();
  expect(host2.querySelector("canvas")).not.toBeNull();
  expect(gl.loop).not.toHaveBeenLastCalledWith(null);
});

it("an older load resolving after a newer one never takes the canvas", async () => {
  let release: (r: Response) => void = () => {};
  vi.mocked(fetch)
    .mockImplementationOnce(() => new Promise<Response>((r) => (release = r)))
    .mockImplementation(async () => ok());
  const [host1, host2] = [document.createElement("div"), document.createElement("div")];
  const slow = (await begin(host1)).promise;
  const settled = expect(slow).rejects.toThrow();
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  await start(host2);
  release(ok());
  await settled;
  expect(host1.querySelector("canvas")).toBeNull();
  expect(host2.querySelector("canvas")).not.toBeNull();
  expect(gl.loop).not.toHaveBeenLastCalledWith(null);
});

it("reports webglcontextlost once and drops the shared renderer", async () => {
  const { host, onLost, promise } = await begin();
  await promise;
  host.querySelector("canvas")?.dispatchEvent(new Event("webglcontextlost", { cancelable: true }));
  expect(onLost).toHaveBeenCalledTimes(1);
  await start(host);
  expect(gl.ctor).toHaveBeenCalledTimes(2);
});

it("recreates the renderer when its context was lost while no viewer was open", async () => {
  (await start()).dispose();
  gl.lost = true;
  gl.rendererDispose.mockImplementation(() => void (gl.lost = false)); // the new renderer is healthy
  await start();
  expect(gl.ctor).toHaveBeenCalledTimes(2);
  expect(gl.rendererDispose).toHaveBeenCalledTimes(1);
});

it("opens wide on a phone, level, facing the liveliest part of the panorama", async () => {
  vi.stubGlobal("innerWidth", 390);
  vi.stubGlobal("innerHeight", 844);
  gl.yaw.mockResolvedValue(HUMP);
  gl.camera.fov = 30;
  await start();
  expect(gl.yaw).toHaveBeenCalledWith(WORLD.panoUrl, expect.any(AbortSignal));
  expect(gl.camera.fov).toBe(100);
  expect(gl.camera.rotation.set).toHaveBeenLastCalledWith(0, yawOf(10), 0, "YXZ");
});

it("puts the camera behind the aim by the step back, along the opposite of where it looks", async () => {
  gl.view = () => ({ yaw: 0.7, back: 2 });
  await start();
  expect(gl.camera.rotation.set).toHaveBeenLastCalledWith(0, 0.7, 0, "YXZ");
  expect(gl.camera.position.set).toHaveBeenLastCalledWith(Math.sin(0.7) * 2, 0, Math.cos(0.7) * 2);
});

it("turns away from a close object in the liveliest direction, for the next liveliest", async () => {
  const { Quaternion, Vector3 } = await vi.importActual<typeof import("three")>("three");
  Object.assign(gl.mesh, { quaternion: new Quaternion(1, 0, 0, 0) }); // the file is Y-down
  const splats: InstanceType<typeof Vector3>[] = [];
  for (let c = 0; c < 64; c++) {
    const close = c >= 2 && c <= 18;
    for (let i = 0; i < 20; i++) {
      const d = close && i < 6 ? 0.3 : 10;
      // file frame: y and z are the world's, mirrored
      splats.push(new Vector3(-d * Math.sin(yawOf(c)), 0, d * Math.cos(yawOf(c))));
    }
  }
  gl.mesh.packedSplats.numSplats = splats.length;
  gl.mesh.packedSplats.getSplat.mockImplementation((i: number) => ({
    center: splats[i],
  }));
  gl.yaw.mockResolvedValue(HUMP.map((v, c) => (c >= 39 && c <= 41 ? 0.5 : v)));
  await start();
  const yaw = gl.camera.rotation.set.mock.calls.at(-1)?.[1] as number;
  expect(Math.abs(yaw - yawOf(40))).toBeLessThan(0.2);
});

it("lowers the pixel ratio once when frames stay slow", async () => {
  await start();
  const frame = gl.loop.mock.calls.at(-1)?.[0] as (t: number) => void;
  gl.ratio.mockClear();
  for (let i = 0; i <= 240; i++) frame(i * 50);
  expect(gl.ratio.mock.calls).toEqual([[1.5]]);
});

it("does not measure the first frame after the page was hidden", async () => {
  await start();
  const frame = gl.loop.mock.calls.at(-1)?.[0] as (t: number) => void;
  gl.ratio.mockClear();
  let t = 0;
  for (let i = 0; i < 119; i++) frame((t += 16));
  document.dispatchEvent(new Event("visibilitychange"));
  frame((t += 10_000));
  for (let i = 0; i < 120; i++) frame((t += 16));
  expect(gl.ratio).not.toHaveBeenCalled();
});

it("stops listening for visibility once the viewer is disposed", async () => {
  const remove = vi.spyOn(document, "removeEventListener");
  (await start()).dispose();
  expect(remove).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
});

it("stops the panorama read when the world fails to load", async () => {
  vi.mocked(fetch).mockResolvedValueOnce(new Response("", { status: 404 }));
  await expect((await begin()).promise).rejects.toThrow();
  const reading = gl.yaw.mock.calls[0]?.[1] as AbortSignal;
  expect(reading.aborted).toBe(true);
});

it("loads the library file when the family's own file fails, and says nothing", async () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.mocked(fetch).mockResolvedValueOnce(new Response("", { status: 404 }));
  const { startViewer } = await import("@/lib/world-3d-viewer");
  const viewer = await startViewer(
    document.createElement("div"),
    {
      spzUrl: "/api/v1/media/own.spz",
      fallbackSpzUrl: "/worlds/x/w.spz",
      panoUrl: "/p.webp",
    },
    vi.fn(),
    new AbortController().signal,
  );
  expect(vi.mocked(fetch).mock.calls.map(([u]) => u)).toEqual([
    "/api/v1/media/own.spz",
    "/worlds/x/w.spz",
  ]);
  expect(warn).toHaveBeenCalled();
  viewer.dispose();
});

it("does not try the library file after an abort", async () => {
  const ctl = new AbortController();
  vi.mocked(fetch).mockImplementationOnce(async () => {
    ctl.abort();
    throw ctl.signal.reason;
  });
  const { startViewer } = await import("@/lib/world-3d-viewer");
  await expect(
    startViewer(
      document.createElement("div"),
      { spzUrl: "/own.spz", fallbackSpzUrl: "/lib.spz", panoUrl: "/p.webp" },
      vi.fn(),
      ctl.signal,
    ),
  ).rejects.toThrow();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("goes straight to the panorama when WebGL2 is missing or init times out", async () => {
  const { startViewer } = await import("@/lib/world-3d-viewer");
  const world = { spzUrl: "/own.spz", fallbackSpzUrl: "/lib.spz", panoUrl: "/p.webp" };
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(null) as never;
  await expect(
    startViewer(document.createElement("div"), world, vi.fn(), new AbortController().signal),
  ).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();

  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({}) as never;
  vi.useFakeTimers();
  gl.mesh.initialized = new Promise(() => {});
  const settled = expect(
    startViewer(document.createElement("div"), world, vi.fn(), new AbortController().signal),
  ).rejects.toThrow("timeout");
  await vi.advanceTimersByTimeAsync(20_001);
  await settled;
  expect(vi.mocked(fetch).mock.calls.map(([u]) => u)).toEqual(["/own.spz"]);
});
