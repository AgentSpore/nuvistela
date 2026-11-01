import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WaitlistForm } from "@/components/waitlist-form";
import { ApiError } from "@/lib/api";
import { waitlistErrorKey } from "@/lib/waitlist";
import { renderRu } from "./render";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
afterEach(() => fetchMock.mockReset());

const reply = (status: number, body: unknown = { ok: true }) =>
  fetchMock.mockResolvedValue(new Response(JSON.stringify(body), { status }));

async function fill(email = "Mama@Example.com") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Почта взрослого"), email);
  return user;
}

describe("waitlistErrorKey", () => {
  it.each([
    [new ApiError("http", 409), "duplicate"],
    [new ApiError("http", 422), "invalid"],
    [new ApiError("http", 429), "limit"],
    [new ApiError("network", 0), "offline"],
    [new ApiError("http", 500), "generic"],
    [new ApiError("parse", 200), "generic"],
    [new Error("x"), "generic"],
  ])("%s -> %s", (e, key) => expect(waitlistErrorKey(e)).toBe(key));
});

describe("WaitlistForm", () => {
  it("posts email, family size and chosen age bands, then shows success", async () => {
    reply(200);
    renderRu(<WaitlistForm />);
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "6–9 лет" }));
    await user.click(screen.getByRole("button", { name: "3–5 лет" }));
    await user.click(screen.getByRole("button", { name: "Записаться" }));
    expect(await screen.findByText("Вы в списке")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/waitlist");
    expect(JSON.parse(init.body)).toEqual({
      email: "Mama@Example.com",
      family_size: 4,
      kids_age_bands: ["3-5", "6-9"],
      locale: "ru",
    });
  });

  it("blocks an invalid email without calling the API", async () => {
    renderRu(<WaitlistForm />);
    const user = await fill("nope");
    await user.click(screen.getByRole("button", { name: "Записаться" }));
    const input = screen.getByLabelText("Почта взрослого");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/name@example\.com/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("marks chips pressed", async () => {
    renderRu(<WaitlistForm />);
    const chip = screen.getByRole("button", { name: "10–13 лет" });
    expect(chip).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "true");
  });

  it.each([
    [409, "Эта почта уже в списке"],
    [422, "Не получилось принять данные"],
    [429, "Слишком много попыток"],
    [500, "Что-то пошло не так на нашей стороне"],
  ])("shows a human message for HTTP %i and keeps the form", async (status, text) => {
    reply(status, { detail: "x" });
    renderRu(<WaitlistForm />);
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Записаться" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByLabelText("Почта взрослого")).toHaveValue("Mama@Example.com");
  });

  it("shows the offline message when fetch fails, and retry can succeed", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderRu(<WaitlistForm />);
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Записаться" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет связи с интернетом");
    reply(200);
    await user.click(screen.getByRole("button", { name: "Записаться" }));
    await waitFor(() => expect(screen.getByText("Вы в списке")).toBeInTheDocument());
  });
});
