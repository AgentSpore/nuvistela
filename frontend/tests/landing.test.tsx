import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";
import { Landing } from "@/components/landing";
import en from "../messages/en.json";
import ru from "../messages/ru.json";

const cases = [
  {
    locale: "ru",
    messages: ru,
    pitch: "Семейная игра: настоящие дела открывают главы общей истории.",
  },
  {
    locale: "en",
    messages: en,
    pitch: "A family game where real chores unlock chapters of your shared story.",
  },
];

describe("Landing", () => {
  it.each(cases)("renders title and pitch for $locale", ({ locale, messages, pitch }) => {
    render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <Landing />
      </NextIntlClientProvider>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "Kinsaga" }),
    ).toBeInTheDocument();
    expect(screen.getByText(pitch)).toBeInTheDocument();
  });
});
