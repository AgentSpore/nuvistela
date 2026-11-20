import { z } from "zod";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WRITE_TIMEOUT_MS } from "@/lib/adventure-api";
import {
  absoluteInvite,
  acceptInvite,
  ApiError,
  request,
  getMe,
  isAgentMissing,
  listMembers,
  sendAgentMessage,
  createFamily,
} from "@/lib/api";

const member = {
  id: "m1",
  family_id: "f1",
  display_name: "Anna",
  age_band: "adult",
  role: "adult",
  interests: [],
  is_owner: false,
};
const reply = (status: number, body?: unknown) =>
  vi
    .fn()
    .mockResolvedValue(
      new Response(body === undefined ? null : JSON.stringify(body), { status }),
    );

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends cookies and parses /me", async () => {
    const fetchMock = reply(200, member);
    vi.stubGlobal("fetch", fetchMock);
    expect(await getMe()).toEqual({ ...member, is_owner: false });
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: "include" });
  });

  it("posts the family body", async () => {
    const fetchMock = reply(201, {
      family_id: "f1",
      member,
      invite_url: "/api/v1/invite/t",
    });
    vi.stubGlobal("fetch", fetchMock);
    await createFamily({
      title: "T",
      locale: "ru",
      privacy_consent: true,
      display_name: "A",
      interests: [],
    });
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
  });

  it("maps 401 to an http ApiError with status", async () => {
    vi.stubGlobal("fetch", reply(401, { detail: "not authenticated" }));
    await expect(getMe()).rejects.toMatchObject({ kind: "http", status: 401 });
  });

  it("maps a shape mismatch to a parse error", async () => {
    vi.stubGlobal("fetch", reply(200, { id: 1 }));
    await expect(getMe()).rejects.toMatchObject({ kind: "parse" });
  });

  it("maps a rejected fetch to a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(getMe()).rejects.toMatchObject({ kind: "network", status: 0 });
  });

  it.each([404, 501])("treats %i from the agent endpoint as missing", async (status) => {
    vi.stubGlobal("fetch", reply(status));
    const err = await sendAgentMessage("hi").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(isAgentMissing(err)).toBe(true);
  });

  it("does not treat 500 as missing", async () => {
    vi.stubGlobal("fetch", reply(500));
    expect(isAgentMissing(await sendAgentMessage("hi").catch((e: unknown) => e))).toBe(
      false,
    );
  });

  it("resolves invite paths against the page origin, not API_URL", () => {
    expect(absoluteInvite("/api/v1/invite/abc")).toBe(
      `${window.location.origin}/api/v1/invite/abc`,
    );
  });

  it("lists family members", async () => {
    const fetchMock = reply(200, [member]);
    vi.stubGlobal("fetch", fetchMock);
    expect(await listMembers("f1")).toEqual([{ ...member, is_owner: false }]);
    expect(fetchMock.mock.calls[0]?.[0]).toMatch(/\/families\/f1\/members$/);
  });

  it("keeps the fragment in invite links", () => {
    expect(absoluteInvite("/join#abc")).toBe(`${window.location.origin}/join#abc`);
  });

  it("posts the token to /invite/accept and maps 401", async () => {
    const ok = reply(200, member);
    vi.stubGlobal("fetch", ok);
    await acceptInvite("t1");
    expect(ok.mock.calls[0]?.[0]).toMatch(/\/invite\/accept$/);
    expect(JSON.parse(String(ok.mock.calls[0]?.[1]?.body))).toEqual({ token: "t1" });
    vi.stubGlobal("fetch", reply(401, { detail: "invalid invite" }));
    await expect(acceptInvite("t1")).rejects.toMatchObject({ kind: "http", status: 401 });
  });
});

describe("admission refusals", () => {
  it.each(["rate_limited", "daily_full"])("keeps the %s code of a 429", async (code) => {
    vi.stubGlobal("fetch", reply(429, { detail: { code } }));
    await expect(acceptInvite("t1")).rejects.toMatchObject({ status: 429, code });
  });

  it("has no code when the error body is not an admission refusal", async () => {
    vi.stubGlobal(
      "fetch",
      reply(429, { detail: "the game master has reached today's limit" }),
    );
    const e = await acceptInvite("t1").catch((x: unknown) => x);
    expect(e).toMatchObject({ status: 429, code: undefined });
  });
});

const hanging = () =>
  vi.fn(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((_, reject) => {
        const fail = () => reject(new DOMException("", "AbortError"));
        if (init.signal?.aborted) fail();
        init.signal?.addEventListener("abort", fail);
      }),
  );

describe("request timeout", () => {
  afterEach(() => vi.useRealTimers());

  it("gives up a hung fetch as a network error once a timeout is asked for", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hanging());
    const result = request("/x", z.unknown(), undefined, WRITE_TIMEOUT_MS).catch(
      (e: unknown) => e,
    );
    await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS - 1);
    expect(fetch).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await result).toMatchObject({ kind: "network" });
  });

  it("a game master reply that takes 20 s still succeeds: no timeout by default", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) =>
            setTimeout(
              () => resolve(new Response(JSON.stringify({ reply: "Привет" }))),
              20_000,
            ),
          ),
      ),
    );
    const result = sendAgentMessage("Привет").then(
      (r) => r,
      (e: unknown) => e,
    );
    await vi.advanceTimersByTimeAsync(20_000);
    expect(await result).toEqual({ reply: "Привет" });
  });

  it("a caller's own signal aborts, before and after the call starts", async () => {
    vi.stubGlobal("fetch", hanging());
    const own = new AbortController();
    const later = request("/x", z.unknown(), { signal: own.signal }).catch(
      (e: unknown) => e,
    );
    own.abort();
    expect(await later).toMatchObject({ kind: "network" });
    const early = await request("/x", z.unknown(), { signal: own.signal }).catch(
      (e: unknown) => e,
    );
    expect(early).toMatchObject({ kind: "network" });
  });
});
