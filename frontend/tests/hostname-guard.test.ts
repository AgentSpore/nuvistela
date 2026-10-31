import { describe, expect, it } from "vitest";
import { assertServableHostname } from "@/lib/hostname-guard";

describe("assertServableHostname", () => {
  it.each(["127.0.0.1", "127.1.2.3", "::1", "[::1]"])(
    "rejects loopback bind %s (next-intl rewrite loops on 307)",
    (hostname) => {
      expect(() => assertServableHostname(hostname)).toThrow(/HOSTNAME/);
    },
  );

  it.each([undefined, "", "0.0.0.0", "::", "localhost", "bumbli.example.org"])(
    "accepts %s",
    (hostname) => {
      expect(() => assertServableHostname(hostname)).not.toThrow();
    },
  );
});
