import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Adventure } from "@/components/adventure";
import * as api from "@/lib/api";
import * as adv from "@/lib/adventure-api";
import { member, renderRu } from "./render";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getAdventure: vi.fn(),
  getWorld: vi.fn(),
}));
const a = vi.mocked(adv);

const chapter: adv.Chapter = {
  id: "c1",
  seq: 1,
  status: "ready",
  title: "Глава",
  body: "Текст.",
};
const world = {
  title: "Маяк",
  setting: "Тихий городок.",
  prologue: "Добро пожаловать.",
  locations: [],
  heroes: [],
};
const chronicle = [
  { chapter: 1, text: "Станция получила вывеску" },
  { chapter: 3, text: "Зажёгся маяк" },
];

const show = (extra: Partial<adv.Adventure>) => {
  a.getAdventure.mockResolvedValue({
    world: { status: "ready" },
    quest: null,
    chapters: [chapter],
    chronicle: [],
    skills: [],
    ...extra,
  });
  a.getWorld.mockResolvedValue({
    status: "ready",
    genre: "space",
    cover: null,
    world,
  } as adv.WorldResponse);
  renderRu(<Adventure />);
};
const fresh = () => screen.queryAllByText(/^Новое/);

type Watch = { cb: IntersectionObserverCallback; el: Element };
let watches: Watch[] = [];
let store: Map<string, string>;
/** Everything the page watches is on screen at once; `scrolledIn` fires the observers by hand. */
const scrolledIn = () =>
  act(() =>
    watches.forEach((w) =>
      w.cb(
        [{ isIntersecting: true, target: w.el } as IntersectionObserverEntry],
        {} as IntersectionObserver,
      ),
    ),
  );
const stubObserver = (instantly: boolean) => {
  watches = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private cb: IntersectionObserverCallback) {}
      observe(el: Element) {
        watches.push({ cb: this.cb, el });
        if (instantly) scrolledIn();
      }
      disconnect() {}
    },
  );
};
const aboutCard = () => screen.getByText("О мире").closest("details");

beforeEach(() => {
  vi.clearAllMocks();
  store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  });
  stubObserver(true);
  vi.mocked(api.getMe).mockResolvedValue(member());
});
afterEach(() => vi.unstubAllGlobals());

describe("world chronicle and skills", () => {
  it("lists milestones in order and skills, with no numbers", async () => {
    show({ chronicle, skills: ["наблюдательность", "смелость"] });
    const list = await screen.findByRole("list", { name: "Хроника мира" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringContaining("Станция получила вывеску"),
      expect.stringContaining("Зажёгся маяк"),
    ]);
    expect(list.textContent).not.toMatch(/\d/);
    const skills = screen.getByRole("list", { name: "Чему учились" });
    expect(within(skills).getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders neither section when both are empty", async () => {
    show({});
    await screen.findByText("О мире");
    expect(screen.queryByText("Хроника мира")).toBeNull();
    expect(screen.queryByText("Чему учились")).toBeNull();
  });

  it("highlights a new milestone once, then never again for that family", async () => {
    show({ chronicle });
    await screen.findByRole("list", { name: "Хроника мира" });
    expect(fresh()).toHaveLength(2);
    cleanup();
    show({ chronicle });
    await screen.findByText("Станция получила вывеску");
    expect(fresh()).toHaveLength(0);
  });

  it("highlights only the milestone that was not seen before", async () => {
    show({ chronicle: chronicle.slice(0, 1) });
    await screen.findByText("Станция получила вывеску");
    cleanup();
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    const marked = fresh().map((n) => n.closest("li")?.textContent);
    expect(marked).toEqual([expect.stringContaining("Зажёгся маяк")]);
  });

  it("works when localStorage throws", async () => {
    const denied = () => {
      throw new Error("denied");
    };
    vi.stubGlobal("localStorage", { getItem: denied, setItem: denied });
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    expect(fresh()).toHaveLength(2);
  });

  it("opens the card on a return visit for an unseen milestone, closes it once seen", async () => {
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    expect(aboutCard()).toHaveAttribute("open");
    cleanup();
    show({ chronicle });
    await screen.findByText("О мире");
    expect(aboutCard()).not.toHaveAttribute("open");
  });

  it("lets the reader close the card that opened for a new milestone", async () => {
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    fireEvent.click(screen.getByText("О мире"));
    await vi.waitFor(() => expect(aboutCard()).not.toHaveAttribute("open"));
  });

  it("keeps the milestone new until the list has been on screen", async () => {
    stubObserver(false);
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    cleanup();
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    expect(fresh()).toHaveLength(2);
    scrolledIn();
    cleanup();
    show({ chronicle });
    await screen.findByText("О мире");
    expect(aboutCard()).not.toHaveAttribute("open");
  });

  it("keeps what another tab saw in the meantime when it remembers", async () => {
    stubObserver(false);
    show({ chronicle });
    await screen.findByText("Зажёгся маяк");
    store.set(`nuvistela-milestones-seen:${member().family_id}`, "[9]");
    scrolledIn();
    const saved = JSON.parse(
      store.get(`nuvistela-milestones-seen:${member().family_id}`) ?? "[]",
    );
    expect(saved.sort()).toEqual([1, 3, 9]);
  });

  it("marks a new milestone with a sparkle, not colour alone", async () => {
    show({ chronicle: chronicle.slice(0, 1) });
    const item = (await screen.findByText("Станция получила вывеску")).closest("li");
    expect(item?.querySelector("[aria-hidden]")).not.toHaveClass("invisible");
  });
});
