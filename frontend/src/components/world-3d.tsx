"use client";
import { useTranslations } from "next-intl";
import { useMemo, useRef, useState } from "react";
import type { Scene } from "@/lib/adventure-api";
import { worldForScene, type World3dAssets } from "@/lib/world-3d-assets";
import { Button } from "@/components/ui/button";
import { World3dDialog } from "@/components/world-3d-dialog";

const CubeIcon = () => (
  <svg
    width={20}
    height={20}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" />
    <path d="m4 7.5 8 4.5 8-4.5M12 12v9" />
  </svg>
);

/** Message arguments for the size: a ceiling gets the "up to" prefix, an exact size none. */
const sizeArgs = (world: World3dAssets, upTo: string) => ({
  mb: world.megabytes,
  upTo: world.sizeIsCeiling ? upTo : "",
});

/**
 * "Walk through the world" button; imports nothing 3D until the tap. The family's own scene replaces the library world once ready.
 * `corner` is the small icon-and-short-label form for the picture: the size moves to the accessible name.
 */
export function World3d({
  genre,
  scene,
  className,
  corner = false,
}: {
  genre: string;
  scene?: Scene | null;
  className?: string;
  corner?: boolean;
}) {
  const t = useTranslations("adventure.world3d");
  // The world as it was at the tap: a scene turning ready mid-walk only shows on the next open.
  const [opened, setOpened] = useState<World3dAssets | null>(null);
  const [panoramaOnly, setPanoramaOnly] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const spzUrl = scene?.url;
  const panoUrl = scene?.panorama_url;
  // Stable across parent re-renders: a new object would restart the open viewer.
  const world = useMemo(
    () => worldForScene(genre, spzUrl && panoUrl ? { spzUrl, panoUrl } : undefined),
    [genre, spzUrl, panoUrl],
  );
  if (!world) return null;
  const size = sizeArgs(world, t("upTo"));
  return (
    <>
      <Button
        ref={opener}
        variant="ghost"
        className={corner ? `min-w-12 !px-3 ${className ?? ""}` : className}
        aria-label={corner ? t("walkLabel", size) : undefined}
        onClick={() => {
          setPanoramaOnly(new URLSearchParams(window.location.search).has("nogl"));
          setOpened(world);
        }}
      >
        {corner ? (
          <>
            <CubeIcon />
            {t("walkShort")}
          </>
        ) : (
          t("walk", size)
        )}
      </Button>
      {opened && (
        <World3dDialog
          world={opened}
          panoramaOnly={panoramaOnly}
          onClose={() => {
            setOpened(null);
            opener.current?.focus();
          }}
        />
      )}
    </>
  );
}
