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
    expect(screen.getByText(messages.landing.pitch)).toBeInTheDocument();
  });
});
