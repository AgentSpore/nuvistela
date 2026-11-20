import { describe, expect, it, vi } from "vitest";
import { Landing } from "@/components/landing";
import { exampleLoader } from "@/lib/example-loader";
import { renderRu } from "./render";

vi.mock("@/i18n/navigation", async (original) => ({
  ...(await original<typeof import("@/i18n/navigation")>()),
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn() }),
}));

describe("landing above the fold", () => {
  it("paints hero text and image without an entrance fade", () => {
    const { container } = renderRu(<Landing />);
    const hero = container.querySelector("main > section");
    expect(hero?.querySelectorAll(".rise")).toHaveLength(0);
  });

  it("hero image is high priority and srcset-driven", () => {
    const { container } = renderRu(<Landing />);
    const img = container.querySelector("main > section img");
    expect(img?.getAttribute("fetchpriority")).toBe("high");
    expect(img?.getAttribute("sizes")).toBeTruthy();
    expect(img?.getAttribute("srcset")).toContain("hero-rainbow-640.webp");
  });

  it("gallery images are lazy, sized and never serve 768px to a phone", () => {
    const { container } = renderRu(<Landing />);
    const imgs = [...container.querySelectorAll("section[aria-labelledby=gal-h] img")];
    expect(imgs).toHaveLength(4);
    for (const img of imgs) {
      expect(img.getAttribute("loading")).toBe("lazy");
      expect(img.getAttribute("sizes")).toContain("50vw");
      expect(img.getAttribute("srcset")).toMatch(/-360\.webp \d+w/);
    }
  });
});

describe("exampleLoader", () => {
  it.each([
    [200, "/examples/ship-360.webp"],
    [360, "/examples/ship-360.webp"],
    [384, "/examples/ship-360.webp"],
    [385, "/examples/ship-640.webp"],
    [640, "/examples/ship-640.webp"],
    [750, "/examples/ship.webp"],
    [3840, "/examples/ship.webp"],
  ])("width %i -> %s", (width, url) => {
    expect(exampleLoader({ src: "/examples/ship.webp", width })).toBe(url);
  });
});
