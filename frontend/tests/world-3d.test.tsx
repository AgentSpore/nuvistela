import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { World3d } from "@/components/world-3d";
import { World3dDialog } from "@/components/world-3d-dialog";
import { NextIntlClientProvider } from "next-intl";
import { renderRu } from "./render";
import en from "../messages/en.json";
import ru from "../messages/ru.json";

const viewer = vi.hoisted(() => ({
  loaded: vi.fn(),
  start: vi.fn(),
  factory: () => {
    viewer.loaded();
    return { startViewer: viewer.start };
  },
}));
vi.mock("@/lib/world-3d-viewer", () => viewer.factory());

const dispose = vi.fn();
const WALK = /Пройтись по миру · (до )?\d+ МБ/;

beforeEach(() => {
  viewer.start.mockResolvedValue({ dispose });
});
afterEach(() => {
  vi.restoreAllMocks();
  viewer.loaded.mockClear();
  viewer.start.mockReset();
  dispose.mockClear();
  window.history.replaceState(null, "", "/");
});

it("draws no button for a genre without a world", () => {
  renderRu(<World3d genre="space" />);
  expect(screen.queryByRole("button")).toBeNull();
});

async function freshWorld3d() {
  vi.resetModules();
  vi.doMock("@/lib/world-3d-viewer", viewer.factory);
  viewer.loaded.mockClear();
  return (await import("@/components/world-3d")).World3d;
}

it("shows the size of the download on the button and loads nothing before the tap", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  const Fresh = await freshWorld3d();
  renderRu(<Fresh genre="pirates" />);
  expect(
    screen.getByRole("button", { name: "Пройтись по миру · 7 МБ" }),
  ).toBeInTheDocument();
  expect(viewer.loaded).not.toHaveBeenCalled();
  expect(fetchSpy).not.toHaveBeenCalled();
});

it("imports the viewer chunk on the tap, not before", async () => {
  const Fresh = await freshWorld3d();
  renderRu(<Fresh genre="pirates" />);
  expect(viewer.loaded).toHaveBeenCalledTimes(0);
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(1));
  expect(viewer.loaded).toHaveBeenCalledTimes(1);
  expect(viewer.start.mock.calls[0]?.[1].spzUrl).toMatch(
    /\/worlds\/seaside-lighthouse\/.+\.spz$/,
  );
});

async function expectPanoramaWithoutError() {
  const pano = await screen.findByRole("img", { name: "Панорама мира" });
  expect(pano).toHaveAttribute(
    "src",
    expect.stringMatching(/\/worlds\/.+\/pano\..+\.webp$/),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByRole("status")).toBeNull();
  expect(document.body.textContent).not.toMatch(/ошибк|не удалось/i);
}

it("falls back to the panorama when the viewer rejects (404, no WebGL2, timeout)", async () => {
  viewer.start.mockRejectedValue(new Error("spz 404"));
  renderRu(<World3d genre="custom" />);
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await expectPanoramaWithoutError();
});

it("falls back to the panorama when the context is lost after start", async () => {
  renderRu(<World3d genre="pirates" />);
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalled());
  viewer.start.mock.calls[0]?.[2]();
  await expectPanoramaWithoutError();
});

it("?nogl shows the panorama without importing the viewer", async () => {
  window.history.replaceState(null, "", "/?nogl");
  const Fresh = await freshWorld3d();
  renderRu(<Fresh genre="pirates" />);
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await expectPanoramaWithoutError();
  expect(viewer.loaded).not.toHaveBeenCalled();
});

it("closing while the viewer loads aborts it", async () => {
  viewer.start.mockReturnValue(new Promise(() => {}));
  renderRu(<World3d genre="pirates" />);
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalled());
  const signal: AbortSignal = viewer.start.mock.calls[0]?.[3];
  expect(signal.aborted).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Закрыть" }));
  expect(signal.aborted).toBe(true);
});

it("a first load aborted by an effect re-run does not flip the mounted dialog to the panorama", async () => {
  viewer.start.mockImplementation(
    (_host: unknown, _world: unknown, _lost: unknown, signal: AbortSignal) =>
      new Promise((_, reject) =>
        signal.addEventListener("abort", () => reject(signal.reason)),
      ),
  );
  const assets = (spzUrl: string) => ({
    spzUrl,
    panoUrl: "/worlds/x/pano.webp",
    thumbUrl: "/worlds/x/thumb.webp",
    megabytes: 7,
    sizeIsCeiling: false,
  });
  const dialog = (spzUrl: string) => (
    <NextIntlClientProvider locale="ru" messages={ru}>
      <World3dDialog world={assets(spzUrl)} panoramaOnly={false} onClose={() => {}} />
    </NextIntlClientProvider>
  );
  const { rerender } = render(dialog("/worlds/x/a.spz"));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(1));
  rerender(dialog("/worlds/x/b.spz"));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(2));
  expect(viewer.start.mock.calls[0]?.[3].aborted).toBe(true);
  await act(async () => {});
  expect(screen.getByRole("dialog", { hidden: true })).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "Панорама мира", hidden: true })).toBeNull();
});

it("close disposes the viewer and returns focus to the button", async () => {
  renderRu(<World3d genre="pirates" />);
  const button = screen.getByRole("button", { name: WALK });
  await userEvent.click(button);
  await waitFor(() => expect(viewer.start).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("button", { name: "Закрыть" }));
  expect(dispose).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(button).toHaveFocus();
});

it("Escape closes and disposes", async () => {
  renderRu(<World3d genre="pirates" />);
  const button = screen.getByRole("button", { name: WALK });
  await userEvent.click(button);
  await waitFor(() => expect(viewer.start).toHaveBeenCalled());
  await userEvent.keyboard("{Escape}");
  expect(dispose).toHaveBeenCalledTimes(1);
  expect(button).toHaveFocus();
});

const H = "b".repeat(64);
const OWN = {
  status: "ready" as const,
  url: `/api/v1/media/${H}.spz`,
  panorama_url: `/api/v1/media/pano/${H}.webp`,
};

it("opens the family's own file, with the library one as the quiet fallback", async () => {
  renderRu(<World3d genre="pirates" scene={OWN} />);
  await userEvent.click(screen.getByRole("button", { name: /Пройтись по миру/ }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(1));
  const world = viewer.start.mock.calls[0]?.[1];
  expect(world.spzUrl).toBe(OWN.url);
  expect(world.fallbackSpzUrl).toMatch(/\/worlds\/seaside-lighthouse\/.+\.spz$/);
});

it("shows the family's own panorama when 3D cannot run", async () => {
  window.history.replaceState(null, "", "/?nogl");
  renderRu(<World3d genre="pirates" scene={OWN} />);
  await userEvent.click(screen.getByRole("button", { name: /Пройтись по миру/ }));
  expect(await screen.findByRole("img", { name: "Панорама мира" })).toHaveAttribute(
    "src",
    OWN.panorama_url,
  );
});

it("gives a genre without a library world a button once its own scene is ready", () => {
  const { unmount } = renderRu(<World3d genre="space" scene={null} />);
  expect(screen.queryByRole("button")).toBeNull();
  unmount();
  renderRu(<World3d genre="space" scene={OWN} />);
  expect(screen.getByRole("button", { name: /Пройтись по миру/ })).toBeInTheDocument();
});

it("a scene turning ready while the dialog is open does not restart the walk", async () => {
  const withScene = (scene: typeof OWN | null) => (
    <NextIntlClientProvider locale="ru" messages={ru}>
      <World3d genre="pirates" scene={scene} />
    </NextIntlClientProvider>
  );
  const { rerender } = render(withScene(null));
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(1));
  expect(viewer.start.mock.calls[0]?.[1].spzUrl).toMatch(/\/worlds\//);
  rerender(withScene(OWN));
  await act(async () => {});
  expect(viewer.start).toHaveBeenCalledTimes(1);
  expect(viewer.start.mock.calls[0]?.[3].aborted).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Закрыть" }));
  await userEvent.click(screen.getByRole("button", { name: /Пройтись по миру/ }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(2));
  expect(viewer.start.mock.calls[1]?.[1].spzUrl).toBe(OWN.url);
});

it("a re-render with the same scene does not restart the open viewer", async () => {
  const tree = (
    <NextIntlClientProvider locale="ru" messages={ru}>
      <World3d genre="pirates" scene={{ ...OWN }} />
    </NextIntlClientProvider>
  );
  const { rerender } = renderRu(<World3d genre="pirates" scene={{ ...OWN }} />);
  await userEvent.click(screen.getByRole("button", { name: /Пройтись по миру/ }));
  await waitFor(() => expect(viewer.start).toHaveBeenCalledTimes(1));
  rerender(tree);
  await act(async () => {});
  expect(viewer.start).toHaveBeenCalledTimes(1);
});

it("has the strings in ru and en", () => {
  for (const m of [ru, en]) {
    const s = m.adventure.world3d;
    for (const k of ["walk", "close", "panoAlt"] as const) expect(s[k]).toBeTruthy();
  }
  expect(en.adventure.world3d.walk).toContain("{mb}");
  expect(ru.adventure.world3d.walk).toContain("{mb}");
});

// Last on purpose: doMock replaces the file-wide mock for the rest of the module.
it("falls back to the panorama when the viewer chunk fails to import", async () => {
  vi.resetModules();
  vi.doMock("@/lib/world-3d-viewer", () => {
    throw new Error("chunk failed");
  });
  renderRu(<World3d genre="fairy_tale" />);
  await userEvent.click(screen.getByRole("button", { name: WALK }));
  await expectPanoramaWithoutError();
});
