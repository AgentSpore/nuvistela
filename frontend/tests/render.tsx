import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import type { Member } from "@/lib/api";
import ru from "../messages/ru.json";

export const renderRu = (ui: ReactElement) =>
  render(
    <NextIntlClientProvider locale="ru" messages={ru}>
      {ui}
    </NextIntlClientProvider>,
  );

export const member = (over: Partial<Member> = {}): Member => ({
  id: "m1",
  family_id: "f1",
  display_name: "Анна",
  age_band: "adult",
  role: "adult",
  interests: [],
  ...over,
});
