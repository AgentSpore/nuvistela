export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

/** Mirrors the backend default `agent_max_text_chars`. */
export const MAX_MESSAGE_CHARS = 2000;

/** Public name of the product. Page copy lives in messages/*.json; this feeds the logo and footer. */
export const BRAND = "Nuvistela";

/** Public origin for absolute link-preview URLs; chat apps and X reject relative ones. */
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://nuvistela.agentspore.com"
).replace(/\/+$/, "");
