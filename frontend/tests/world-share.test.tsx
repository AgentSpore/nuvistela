import { configure, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { WorldPanel } from "@/components/world-panel";
import * as adventure from "@/lib/adventure-api";
import * as api from "@/lib/api";
import * as share from "@/lib/share-api";
import { member, renderRu } from "./render";

// The first render of WorldPanel is slow under a parallel full-suite run; 1 s default flakes.
configure({ asyncUtilTimeout: 5000 });

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  getMe: vi.fn(),
}));
vi.mock("@/lib/adventure-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/adventure-api")>()),
  getWorld: vi.fn(),
}));
vi.mock("@/lib/share-api", async (orig) => ({
  ...(await orig<typeof import("@/lib/share-api")>()),
  getShareState: vi.fn(),
  createShare: vi.fn(),
  revokeShare: vi.fn(),
}));

const TOKEN = "AbCdEfGhIjKlMnOpQrStUv";
const STATE = {
  title: "Тихая бухта",
  genre: "pirates",
  token: null,
  other_active: false,
  quests_done: 0,
  chapters: 0,
} as const;
const READY = { status: "ready", url: `/api/v1/media/${"a".repeat(64)}.webp` } as const;

function world(cover: adventure.WorldResponse["cover"]): adventure.WorldResponse {
  return {
    status: "ready",
    genre: "pirates",
    cover,
    world: {
      title: "Тихая бухта",
      setting: "s",
      prologue: "p",
      locations: [],
      heroes: [],
    },
  };
}

function setup(
  over: { role?: "adult" | "child"; cover?: adventure.WorldResponse["cover"] } = {},
) {
  vi.mocked(api.getMe).mockResolvedValue(member({ role: over.role ?? "adult" }));
  vi.mocked(adventure.getWorld).mockResolvedValue(
    world(over.cover === undefined ? READY : over.cover),
  );
  return renderRu(
    <WorldPanel
      familyId="f1"
      status="ready"
      memberId="m1"
      firstVisit={false}
      slow={false}
    />,
  );
}

async function createButton() {
  const button = await screen.findByRole("button", { name: "Создать ссылку" });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

let writeText = vi.fn();
let shareFn: ((data: ShareData) => Promise<void>) | undefined;

async function openSheet() {
  const user = userEvent.setup(); // installs its own clipboard: stub ours after it
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  Object.defineProperty(navigator, "share", { value: shareFn, configurable: true });
  await user.click(await screen.findByRole("button", { name: "Поделиться миром" }));
  return user;
}

beforeEach(() => {
  vi.mocked(share.createShare).mockResolvedValue({ token: TOKEN, created: true });
  vi.mocked(share.revokeShare).mockResolvedValue();
  vi.mocked(share.getShareState).mockResolvedValue(STATE);
  writeText = vi.fn().mockResolvedValue(undefined);
  shareFn = undefined;
});
afterEach(() => vi.clearAllMocks());

it("gives an adult with a ready cover the button, and the sheet shows the card and the consent line", async () => {
  setup();
  await openSheet();
  expect(screen.getByRole("dialog", { name: "Поделиться миром" })).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { name: "Тихая бухта" }).length).toBeGreaterThan(
    0,
  );
  expect(
    screen.getByText("Видят все, у кого есть ссылка. Ссылку можно отключить"),
  ).toBeInTheDocument();
});

it("previews the vetted title: genre words when the server dropped a name from it", async () => {
  vi.mocked(share.getShareState).mockResolvedValue({ ...STATE, title: null });
  setup();
  await openSheet();
  const dialog = screen.getByRole("dialog");
  expect(
    await within(dialog).findByRole("heading", { name: "Пираты" }),
  ).toBeInTheDocument();
  expect(within(dialog).queryByText("Тихая бухта")).toBeNull();
  expect(dialog.querySelector("main")).toBeNull();
});

it("shows the active link with the turn-off button on open, without pressing create", async () => {
  vi.mocked(share.getShareState).mockResolvedValue({ ...STATE, token: TOKEN });
  setup();
  await openSheet();
  expect(await screen.findByLabelText("Ссылка на открытку")).toHaveValue(
    `${window.location.origin}/ru/w/${TOKEN}`,
  );
  expect(screen.getByRole("button", { name: "Отключить ссылку" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Создать ссылку" })).toBeNull();
  expect(share.createShare).not.toHaveBeenCalled();
});

it("offers to turn off an older world's link that the sheet cannot show", async () => {
  vi.mocked(share.getShareState).mockResolvedValue({ ...STATE, other_active: true });
  setup();
  const user = await openSheet();
  await user.click(await screen.findByRole("button", { name: "Отключить ссылку" }));
  await user.click(screen.getByRole("button", { name: "Да, отключить" }));
  expect(share.revokeShare).toHaveBeenCalledWith("f1");
  expect(await screen.findByText(/Ссылка отключена/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Отключить ссылку" })).toBeNull();
  expect(screen.queryByRole("group", { name: "Отключить ссылку" })).toBeNull();
});

it("marks the sheet busy while a request runs", async () => {
  vi.mocked(share.createShare).mockReturnValue(new Promise(() => {}));
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
});

it("cannot create while the preview is not loaded, and says so when loading fails", async () => {
  vi.mocked(share.getShareState).mockRejectedValue(new api.ApiError("http", 409));
  setup();
  await openSheet();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /у мира нет готовой картинки/,
  );
  expect(screen.getByRole("button", { name: "Создать ссылку" })).toBeDisabled();
});

it("sends one create request however many times the button is pressed", async () => {
  let resolve: (v: { token: string; created: boolean }) => void = () => {};
  vi.mocked(share.createShare).mockReturnValue(new Promise((r) => (resolve = r)));
  setup();
  const user = await openSheet();
  const button = await createButton();
  await user.click(button);
  await user.click(button);
  expect(share.createShare).toHaveBeenCalledTimes(1);
  expect(button).toBeDisabled();
  resolve({ token: TOKEN, created: true });
  expect(await screen.findByLabelText("Ссылка на открытку")).toBeInTheDocument();
});

it("shows a child no share button", async () => {
  setup({ role: "child" });
  await screen.findByRole("heading", { name: /Тихая бухта/ });
  await waitFor(() => expect(api.getMe).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Поделиться миром" })).toBeNull();
});

it.each([
  ["no cover", null],
  ["a pending cover", { status: "pending", url: null } as const],
  ["a failed cover", { status: "failed", url: null } as const],
])("shows no share button with %s", async (_name, cover) => {
  setup({ cover });
  await screen.findByRole("heading", { name: /Тихая бухта/ });
  // With no cover box there is no share entry to mount, so nobody asks for the member.
  if (cover !== null) await waitFor(() => expect(api.getMe).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Поделиться миром" })).toBeNull();
});

it("copies the link on the page's origin when the browser has no share dialog", async () => {
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  const url = `${window.location.origin}/ru/w/${TOKEN}`;
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(url));
  expect(screen.getByText(/Ссылка скопирована/)).toBeInTheDocument();
});

it("treats cancelling the share dialog as no error", async () => {
  shareFn = vi.fn().mockRejectedValue(new DOMException("x", "AbortError"));
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  expect(await screen.findByText(/Отправка отменена/)).toBeInTheDocument();
  expect(shareFn).toHaveBeenCalledWith({
    url: `${window.location.origin}/ru/w/${TOKEN}`,
  });
  expect(screen.queryByText(/Не удалось/)).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("shows the link as selectable text when the clipboard refuses", async () => {
  writeText = vi.fn().mockRejectedValue(new Error("denied"));
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  expect(await screen.findByText(/Не удалось открыть отправку/)).toBeInTheDocument();
  expect(screen.getByLabelText("Ссылка на открытку")).toHaveValue(
    `${window.location.origin}/ru/w/${TOKEN}`,
  );
});

it("revokes only after confirmation inside the sheet, then the link is gone", async () => {
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  await screen.findByLabelText("Ссылка на открытку");
  await user.click(screen.getByRole("button", { name: "Отключить ссылку" }));
  expect(share.revokeShare).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Да, отключить" }));
  expect(await screen.findByText(/Ссылка отключена/)).toBeInTheDocument();
  expect(share.revokeShare).toHaveBeenCalledWith("f1");
  expect(screen.queryByLabelText("Ссылка на открытку")).toBeNull();
  expect(screen.getByRole("button", { name: "Создать ссылку" })).toBeInTheDocument();
});

it("keeps the link when the adult declines to turn it off", async () => {
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  await screen.findByLabelText("Ссылка на открытку");
  await user.click(screen.getByRole("button", { name: "Отключить ссылку" }));
  await user.click(screen.getByRole("button", { name: "Оставить" }));
  expect(share.revokeShare).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Ссылка на открытку")).toBeInTheDocument();
});

it.each([
  [409, /у мира нет готовой картинки/],
  [429, /Сегодня создано много ссылок/],
  [500, /Не получилось/],
])("explains a %s in plain words and creates no link", async (status, text) => {
  vi.mocked(share.createShare).mockRejectedValue(new api.ApiError("http", status));
  setup();
  const user = await openSheet();
  await user.click(await createButton());
  expect(await screen.findByRole("alert")).toHaveTextContent(text);
  expect(screen.queryByLabelText("Ссылка на открытку")).toBeNull();
});

it("previews the counter line exactly as the public card shows it", async () => {
  vi.mocked(share.getShareState).mockResolvedValue({
    ...STATE,
    quests_done: 5,
    chapters: 21,
  });
  setup();
  await openSheet();
  const dialog = screen.getByRole("dialog");
  await within(dialog).findByRole("heading", { name: "Тихая бухта" });
  expect(dialog.querySelector("[data-share-counts]")).toHaveTextContent(
    "5 дел выполнено · 21 глава",
  );
});
