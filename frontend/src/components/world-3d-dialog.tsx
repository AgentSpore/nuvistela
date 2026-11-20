"use client";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import type { World3dAssets } from "@/lib/world-3d-assets";
import { Button } from "@/components/ui/button";

/** Drag-to-pan strip; native touch scroll on phones, pointer drag for the mouse. */
function Panorama({ src }: { src: string }) {
  const t = useTranslations("adventure.world3d");
  const strip = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; left: number } | null>(null);
  const centre = () => {
    const el = strip.current;
    if (el) el.scrollLeft = (el.scrollWidth - el.clientWidth) / 2;
  };
  return (
    <div
      ref={strip}
      role="region"
      aria-label={t("label")}
      tabIndex={0}
      className="absolute inset-0 cursor-grab touch-pan-x overflow-x-auto overflow-y-hidden"
      onPointerDown={(e) => {
        drag.current = { x: e.clientX, left: e.currentTarget.scrollLeft };
      }}
      onPointerMove={(e) => {
        if (drag.current && e.pointerType === "mouse")
          e.currentTarget.scrollLeft = drag.current.left - (e.clientX - drag.current.x);
      }}
      onPointerUp={() => (drag.current = null)}
      onPointerLeave={() => (drag.current = null)}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- a 4096 px strip scrolled sideways, not a responsive image */}
      <img
        src={src}
        alt={t("panoAlt")}
        draggable={false}
        onLoad={centre}
        className="h-full w-auto max-w-none select-none"
      />
    </div>
  );
}

type Props = { world: World3dAssets; panoramaOnly: boolean; onClose: () => void };
type Mode = "loading" | "viewer" | "panorama";

/** Fullscreen layer: the 3D viewer, or the panorama when 3D cannot run. Never an error text. */
export function World3dDialog({ world, panoramaOnly, onClose }: Props) {
  const t = useTranslations("adventure.world3d");
  const dialog = useRef<HTMLDialogElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<Mode>(panoramaOnly ? "panorama" : "loading");

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
  }, []);

  useEffect(() => {
    if (panoramaOnly) return;
    const abort = new AbortController();
    let dispose: (() => void) | undefined;
    const lost = () => setMode("panorama");
    import("@/lib/world-3d-viewer")
      .then((m) => m.startViewer(host.current as HTMLElement, world, lost, abort.signal))
      .then((viewer) => {
        if (abort.signal.aborted) return viewer.dispose();
        dispose = viewer.dispose;
        setMode("viewer");
      })
      .catch(() => !abort.signal.aborted && setMode("panorama"));
    return () => {
      abort.abort();
      dispose?.();
    };
  }, [world, panoramaOnly]);

  return (
    <dialog
      ref={dialog}
      aria-label={t("label")}
      onClose={onClose}
      style={{ backgroundImage: `url(${world.thumbUrl})` }}
      className="fixed inset-0 m-0 h-dvh max-h-none w-dvw max-w-none bg-black bg-cover bg-center p-0 backdrop:bg-black"
    >
      {mode === "panorama" ? (
        <Panorama src={world.panoUrl} />
      ) : (
        <div ref={host} className="absolute inset-0 touch-none" />
      )}
      <Button
        variant="ghost"
        className="absolute right-4 top-4 z-10"
        onClick={() => dialog.current?.close()}
      >
        {t("close")}
      </Button>
    </dialog>
  );
}
