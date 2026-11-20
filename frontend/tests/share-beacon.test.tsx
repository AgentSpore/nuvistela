import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ShareBeacon } from "@/app/[locale]/(card)/w/[token]/share-beacon";

const record = vi.hoisted(() => vi.fn());
vi.mock("@/lib/pilot-events", () => ({ recordPilotEvent: record }));

const TOKEN = "AbCdEfGhIjKlMnOpQrStUv";
beforeEach(() => {
  record.mockReset();
  sessionStorage.clear();
});

describe("share card beacon", () => {
  it("counts a view once per browser session, also after a reload", () => {
    render(<ShareBeacon token={TOKEN} locale="ru" />).unmount();
    render(<ShareBeacon token={TOKEN} locale="ru" />);
    expect(record).toHaveBeenCalledTimes(1);
    expect(record).toHaveBeenCalledWith("share_viewed", "ru", null, "share");
  });

  it("counts another link separately", () => {
    render(<ShareBeacon token={TOKEN} locale="ru" />);
    render(<ShareBeacon token={`${TOKEN.slice(1)}Z`} locale="en" />);
    expect(record).toHaveBeenCalledTimes(2);
  });

  it("keeps the token out of the stored guard key", () => {
    render(<ShareBeacon token={TOKEN} locale="ru" />);
    const keys = Object.keys(sessionStorage).join();
    expect(keys).not.toContain(TOKEN);
    expect(keys).not.toBe("");
  });

  it("still counts when storage is denied", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied");
    });
    render(<ShareBeacon token={TOKEN} locale="ru" />);
    expect(record).toHaveBeenCalledTimes(1);
    vi.restoreAllMocks();
  });

  it("counts a click on the create-your-own link, and only that", () => {
    const { container } = render(
      <>
        <ShareBeacon token={TOKEN} locale="ru" />
        <a href="https://example.test/?source=share#demo" data-share-cta>
          cta
        </a>
        <a href="https://example.test/elsewhere">other</a>
      </>,
    );
    record.mockClear();
    fireEvent.click(container.querySelector("[data-share-cta]")!);
    fireEvent.click(container.querySelector("a[href$='/elsewhere']")!);
    expect(record).toHaveBeenCalledTimes(1);
    expect(record).toHaveBeenCalledWith("share_cta", "ru", null, "share");
  });
});
