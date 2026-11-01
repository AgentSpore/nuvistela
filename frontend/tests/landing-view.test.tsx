import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LandingView } from "@/components/landing-view";

const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
vi.stubGlobal("fetch", fetchMock);
afterEach(() => fetchMock.mockClear());

describe("LandingView", () => {
  it("sends landing_view once per page load, even across remounts", () => {
    const first = render(<LandingView locale="ru" />);
    first.unmount();
    render(<LandingView locale="ru" />);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/events");
    expect(JSON.parse(init.body)).toEqual({ kind: "landing_view", locale: "ru" });
  });

  it("swallows a network failure", async () => {
    vi.resetModules();
    const { LandingView: Fresh } = await import("@/components/landing-view");
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    expect(() => render(<Fresh locale="en" />)).not.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
