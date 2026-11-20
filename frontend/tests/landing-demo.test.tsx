import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Landing } from "@/components/landing";
import * as pilot from "@/lib/pilot-events";
import ru from "../messages/ru.json";
import en from "../messages/en.json";
import es from "../messages/es.json";
import zh from "../messages/zh-CN.json";

vi.mock("@/lib/pilot-events", async (original) => ({
  ...(await original<typeof import("@/lib/pilot-events")>()),
  recordPilotEvent: vi.fn().mockResolvedValue(undefined),
}));
const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), { status: 200 }),
  );
  Object.defineProperty(navigator, "share", { configurable: true, value: undefined });
});

async function openChapter() {
  const user = userEvent.setup();
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <Landing />
    </NextIntlClientProvider>,
  );
  const demo = () => within(screen.getByRole("region", { name: en.landing.demo.title }));
  await user.click(demo().getByRole("button", { name: en.landing.demo.solo }));
  await user.click(demo().getByRole("button", { name: en.landing.demo.start }));
  await user.click(demo().getByRole("button", { name: en.landing.demo.complete }));
  return user;
}

it.each([
  { locale: "ru", messages: ru },
  { locale: "en", messages: en },
  { locale: "es", messages: es },
  { locale: "zh-CN", messages: zh },
])(
  "$locale demo works before signup and requires explicit intent",
  async ({ locale, messages }) => {
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <Landing />
      </NextIntlClientProvider>,
    );
    const d = messages.landing.demo;
    const demo = () => within(screen.getByRole("region", { name: d.title }));
    expect(demo().getByRole("button", { name: d.start })).toBeDisabled();
    await user.click(demo().getByRole("button", { name: d.solo }));
    await user.click(demo().getByRole("button", { name: d.start }));
    expect(demo().getByText(d.soloQuest)).toBeVisible();
    await user.click(demo().getByRole("button", { name: d.complete }));
    expect(demo().getByRole("heading", { name: d.chapterTitle })).toHaveFocus();
    expect(demo().getByText(d.sampleNote)).toBeVisible();
    expect(pilot.recordPilotEvent).toHaveBeenCalledWith("demo_start", locale, "solo");
    expect(pilot.recordPilotEvent).toHaveBeenCalledWith("demo_complete", locale, "solo");
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

it("demo sign-up leads to the game, not to a waitlist", async () => {
  await openChapter();
  const links = screen.getAllByRole("link", { name: en.landing.demo.signup });
  expect(links).toHaveLength(2);
  for (const link of links) expect(link).toHaveAttribute("href", "/en/new");
});

describe("safe sharing", () => {
  it("copies only the public localized URL when Web Share is absent", async () => {
    const user = await openChapter();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    history.replaceState(null, "", "/en?email=private#invite-secret");
    await user.click(screen.getByRole("button", { name: en.landing.demo.share }));
    expect(writeText).toHaveBeenCalledWith(`${location.origin}/en?source=share#demo`);
    expect(await screen.findByText(en.landing.demo.shareStatus.copied)).toBeVisible();
  });
  it("treats cancellation neutrally, never copying or claiming delivery", async () => {
    const user = await openChapter();
    const share = vi.fn().mockRejectedValue(new DOMException("cancelled", "AbortError"));
    const writeText = vi.fn();
    Object.defineProperty(navigator, "share", { configurable: true, value: share });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    await user.click(screen.getByRole("button", { name: en.landing.demo.share }));
    expect(await screen.findByText(en.landing.demo.shareStatus.cancelled)).toBeVisible();
    expect(writeText).not.toHaveBeenCalled();
  });
  it("does not equate a resolved native share with delivery", async () => {
    const user = await openChapter();
    Object.defineProperty(navigator, "share", {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
    await user.click(screen.getByRole("button", { name: en.landing.demo.share }));
    expect(await screen.findByText(en.landing.demo.shareStatus.closed)).toBeVisible();
  });
});

it("keeps focus on the pressed intent button and does not remount the demo", async () => {
  const user = userEvent.setup();
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <Landing />
    </NextIntlClientProvider>,
  );
  const d = en.landing.demo;
  const demo = () => within(screen.getByRole("region", { name: d.title }));
  await user.click(demo().getByRole("button", { name: d.solo }));
  expect(demo().getByRole("button", { name: d.solo })).toHaveFocus();
  await user.click(demo().getByRole("button", { name: d.start }));
  await user.click(demo().getByRole("button", { name: d.family }));
  expect(demo().getByRole("button", { name: d.family })).toHaveFocus();
  expect(demo().getByRole("button", { name: d.start })).toBeVisible();
});

it.each([
  { locale: "ru", messages: ru },
  { locale: "en", messages: en },
  { locale: "es", messages: es },
  { locale: "zh-CN", messages: zh },
])(
  "$locale landing starts the game directly and sells no waitlist",
  ({ locale, messages }) => {
    const { container } = render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <Landing />
      </NextIntlClientProvider>,
    );
    const start = screen.getAllByRole("link", { name: messages.landing.ctaTry })[0];
    expect(start).toHaveAttribute("href", expect.stringMatching(/\/new$/));
    expect(container.querySelector("#waitlist")).toBeNull();
    expect(container.textContent).not.toMatch(
      /waitlist|список ожидания|lista de espera|等候名单/i,
    );
  },
);
