"use client";
import { useEffect, useState, type RefObject } from "react";

/** True while the element is entirely inside the viewport; null until the observer has reported once (or without one). */
export function useFullyVisible(ref: RefObject<Element | null>): boolean | null {
  const [visible, setVisible] = useState<boolean | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        const last = entries.at(-1);
        if (last) setVisible(last.intersectionRatio >= 0.99);
      },
      { threshold: [0, 0.99, 1] },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return visible;
}
