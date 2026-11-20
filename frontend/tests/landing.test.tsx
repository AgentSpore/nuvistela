import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { Landing } from "@/components/landing";
import en from "../messages/en.json";
import ru from "../messages/ru.json";
import es from "../messages/es.json";
import zh from "../messages/zh-CN.json";

const navigation = vi.hoisted(() => ({ pathname: "/", replace: vi.fn() }));
vi.mock("@/i18n/navigation", async (original) => ({
  ...(await original<typeof import("@/i18n/navigation")>()),
  usePathname: () => navigation.pathname,
  useRouter: () => ({ replace: navigation.replace }),
}));

const cases = [
  { locale: "es", messages: es },
  { locale: "zh-CN", messages: zh },
  {
    locale: "ru",
    messages: ru,
  },
  {
    locale: "en",
    messages: en,
  },
];

describe("Landing", () => {
  it.each(cases)("renders title and pitch for $locale", ({ locale, messages }) => {
    render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <Landing />
      </NextIntlClientProvider>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: messages.landing.title }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(messages.landing.pitch.replace(/\u00a0/g, " ")),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: messages.landing.demoCta })).toHaveAttribute(
      "href",
      "#demo",
    );
    expect(screen.getByRole("link", { name: messages.landing.ctaTry })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/new$/),
    );
  });
});

it("offers four landing languages and navigates on selection", () => {
  navigation.pathname = "/";
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <LocaleSwitcher />
    </NextIntlClientProvider>,
  );
  const select = screen.getByRole("combobox", { name: en.locale.label });
  expect(screen.getAllByRole("option")).toHaveLength(4);
  fireEvent.change(select, { target: { value: "zh-CN" } });
  expect(navigation.replace).toHaveBeenCalledWith("/", { locale: "zh-CN" });
});

it("offers all four languages on app routes", () => {
  navigation.pathname = "/play";
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <LocaleSwitcher />
    </NextIntlClientProvider>,
  );
  expect(
    screen.getAllByRole("option").map((option) => option.getAttribute("value")),
  ).toEqual(["ru", "en", "es", "zh-CN"]);
  navigation.pathname = "/";
});
