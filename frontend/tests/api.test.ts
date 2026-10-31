import { afterEach, describe, expect, it, vi } from "vitest";
import {
  absoluteInvite,
  ApiError,
  getMe,
  isAgentMissing,
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
    expect(await getMe()).toEqual(member);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: "include" });
  });

  it("posts the family body", async () => {
    const fetchMock = reply(201, {
      family_id: "f1",
      member,
      invite_url: "/api/v1/invite/t",
    });
    vi.stubGlobal("fetch", fetchMock);
    await createFamily({ title: "T", locale: "ru", display_name: "A", interests: [] });
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

  it("resolves relative invite paths against the API origin", () => {
    expect(absoluteInvite("/api/v1/invite/abc")).toBe(
      "http://localhost:8080/api/v1/invite/abc",
    );
  });
});
