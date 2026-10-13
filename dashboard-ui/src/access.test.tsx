// @vitest-environment jsdom
import React from "react";
import { afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { AccessPage } from "./pages";
import { api } from "./api/client";
vi.mock("./api/client", () => ({ api: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("confirms disabling and rolls the optimistic state back on a server error", async () => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  const card = {
    card_uid: "ABCDEF12",
    label: "Test card",
    active: true,
    notes: null,
    created_at: "2026-10-13T12:00:00Z",
    last_seen: null,
  };
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (options?.method === "PATCH") throw new Error("Write rejected");
    if (path === "/rfid/cards") return { cards: [card] };
    if (path.startsWith("/rfid/activity")) return { events: [] };
    return { auth_window: null };
  });
  render(<AccessPage revision={0} events={[]} />);
  await screen.findByRole("button", { name: "Disable Test card" });
  fireEvent.click(screen.getByRole("button", { name: "Disable Test card" }));
  expect(
    screen.getByRole("dialog", { name: "Disable Test card?" }),
  ).toBeTruthy();
  expect(
    vi
      .mocked(api)
      .mock.calls.some(([, options]) => options?.method === "PATCH"),
  ).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
  await screen.findByText("Write rejected");
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Disable Test card" }),
    ).toBeTruthy(),
  );
  expect(screen.getByText("Enabled")).toBeTruthy();
});
