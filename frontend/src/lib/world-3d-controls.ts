import type { PerspectiveCamera } from "three";
import { FOV_MAX, FOV_MIN } from "@/lib/world-3d-view";

const PITCH_MAX = 1.4;
const DRAG_SPEED = 0.005;

/** Look around from the centre of the world (drag) and zoom by field of view (wheel, pinch); starts level at `initialYaw`. */
export function bindControls(
  canvas: HTMLElement,
  camera: PerspectiveCamera,
  initialYaw: number,
): () => void {
  let yaw = initialYaw;
  let pitch = 0;
  camera.rotation.set(pitch, yaw, 0, "YXZ");
  const pointers = new Map<number, { x: number; y: number }>();
  let pinch: { distance: number; fov: number } | null = null;

  const distance = () => {
    const [a, b] = [...pointers.values()];
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
  };
  const setFov = (fov: number) => {
    camera.fov = Math.min(FOV_MAX, Math.max(FOV_MIN, fov));
    camera.updateProjectionMatrix();
  };
  const down = (e: PointerEvent) => {
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) pinch = { distance: distance(), fov: camera.fov };
  };
  const move = (e: PointerEvent) => {
    const last = pointers.get(e.pointerId);
    if (!last) return;
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2 && pinch) {
      setFov((pinch.fov * pinch.distance) / (distance() || 1));
      return;
    }
    yaw += (e.clientX - last.x) * DRAG_SPEED;
    pitch = Math.min(
      PITCH_MAX,
      Math.max(-PITCH_MAX, pitch + (e.clientY - last.y) * DRAG_SPEED),
    );
    camera.rotation.set(pitch, yaw, 0, "YXZ");
  };
  const up = (e: PointerEvent) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
  };
  const wheel = (e: WheelEvent) => {
    e.preventDefault();
    setFov(camera.fov * Math.exp(e.deltaY * 0.001));
  };

  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", up);
  canvas.addEventListener("wheel", wheel, { passive: false });
  return () => {
    canvas.removeEventListener("pointerdown", down);
    canvas.removeEventListener("pointermove", move);
    canvas.removeEventListener("pointerup", up);
    canvas.removeEventListener("pointercancel", up);
    canvas.removeEventListener("wheel", wheel);
  };
}
