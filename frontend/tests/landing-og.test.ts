import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "../messages/en.json";
import es from "../messages/es.json";
import ru from "../messages/ru.json";
import zh from "../messages/zh-CN.json";
import { generateMetadata } from "@/app/[locale]/(site)/page";

const MESSAGES = { ru, en, es, "zh-CN": zh };
type Locale = keyof typeof MESSAGES;

vi.mock("next-intl/server", () => ({
  setRequestLocale: () => undefined,
  getTranslations: async ({ locale, namespace }: { locale: Locale; namespace: "meta" }) =>
    createTranslator({ locale, messages: MESSAGES[locale], namespace }),
}));

const OG_LOCALE = { ru: "ru_RU", en: "en_US", es: "es_ES", "zh-CN": "zh_CN" } as const;
const FORBIDDEN =
  /список ожидания|пилот|прототип|waitlist|pilot|prototype|lista de espera|piloto|prototipo|候补|试点|原型/i;

describe.each(Object.keys(MESSAGES) as Locale[])("landing metadata %s", (locale) => {
  const meta = () => generateMetadata({ params: Promise.resolve({ locale }) });

  it("has full Open Graph and Twitter card on absolute https urls", async () => {
    const m = await meta();
    const og = m.openGraph;
    expect(og).toMatchObject({ type: "website", locale: OG_LOCALE[locale] });
    expect(og?.title).toBeTruthy();
    expect(og?.description).toBeTruthy();
    const image = (og?.images as { url: string; width: number; height: number }[])[0]!;
    expect(image).toMatchObject({ width: 1200, height: 630 });
    expect(image.url).toMatch(/^https:\/\/[^/]+\/og\/og-(ru|en)\.jpg$/);
    expect(String(og?.url)).toMatch(
      new RegExp(`^https://[^/]+/${locale === "ru" ? "" : locale}$`),
    );
    expect(m.twitter).toMatchObject({ card: "summary_large_image", title: og?.title });
    expect(m.twitter?.description).toBe(og?.description);
    expect((m.twitter?.images as { url: string }[])[0]!.url).toBe(image.url);
  });

  it("avoids waitlist/pilot wording in the message texts", () => {
    const { ogTitle, ogDescription, ogImageAlt } = MESSAGES[locale].meta;
    for (const text of [ogTitle, ogDescription, ogImageAlt]) {
      expect(text.length).toBeGreaterThan(0);
      expect(text).not.toMatch(FORBIDDEN);
    }
  });

  it("uses own picture for ru and en, en picture for the rest", async () => {
    const m = await meta();
    const url = (m.openGraph?.images as { url: string }[])[0]!.url;
    expect(url.endsWith(locale === "ru" ? "og-ru.jpg" : "og-en.jpg")).toBe(true);
  });
});

describe("SITE_URL", () => {
  const load = async (value: string) => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", value);
    return (await import("@/lib/config")).SITE_URL;
  };
  afterEach(() => vi.unstubAllEnvs());

  it("falls back to the https default when the variable is empty", async () => {
    expect(await load("")).toBe("https://nuvistela.agentspore.com");
  });

  it("drops trailing slashes", async () => {
    expect(await load("https://example.test//")).toBe("https://example.test");
  });
});
