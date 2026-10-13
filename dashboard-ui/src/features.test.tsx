// @vitest-environment jsdom
import React from "react";
import { afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from "@testing-library/react";
import { EventViews, BackupPanel } from "./featurePanels";
import { addView, parseViews, cleanQuery, VIEW_KEY } from "./api/savedViews";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("validates saved views and excludes pagination or credential fields", () => {
  expect(
    cleanQuery("severity=warning&cursor=99&limit=10&password=secret"),
  ).toBe("severity=warning");
  expect(parseViews("broken")).toEqual([]);
  expect(parseViews('{"name":"not-an-array"}')).toEqual([]);
  expect(addView([], " Front door ", "sensor=entry_monitor&cursor=9")).toEqual([
    { name: "Front door", query: "sensor=entry_monitor" },
  ]);
  expect(() =>
    addView([{ name: "Front door", query: "" }], "front DOOR", ""),
  ).toThrow("already exists");
  expect(() =>
    addView(
      Array.from({ length: 10 }, (_, i) => ({ name: String(i), query: "" })),
      "eleventh",
      "",
    ),
  ).toThrow("up to 10");
});

it("saves, restores and removes a browser-local event view", async () => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  const apply = vi.fn();
  const { unmount } = render(
    <EventViews query="severity=critical&cursor=99" onApply={apply} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Save view" }));
  fireEvent.change(screen.getByLabelText("View name"), {
    target: { value: "Critical signals" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save filters" }));
  expect(JSON.parse(localStorage.getItem(VIEW_KEY)!)).toEqual([
    { name: "Critical signals", query: "severity=critical" },
  ]);
  unmount();
  render(<EventViews query="" onApply={apply} />);
  fireEvent.change(screen.getByLabelText("Saved event views"), {
    target: { value: "Critical signals" },
  });
  expect(apply).toHaveBeenCalledWith("severity=critical");
  fireEvent.click(
    screen.getByRole("button", { name: "Remove saved view Critical signals" }),
  );
  expect(JSON.parse(localStorage.getItem(VIEW_KEY)!)).toEqual([]);
});

it("builds a useful denied-access preset", () => {
  const apply = vi.fn();
  render(<EventViews query="" onApply={apply} />);
  fireEvent.click(screen.getByRole("button", { name: "Denied access" }));
  const params = new URLSearchParams(apply.mock.calls[0][0]);
  expect(params.get("sensor")).toBe("rfid_auth");
  expect(params.get("status")).toBe("card_denied");
  expect(Date.now() - Date.parse(params.get("since")!)).toBeGreaterThanOrEqual(
    3599000,
  );
});

it("clears the saved-view selection when filters are reset manually", () => {
  localStorage.setItem(
    VIEW_KEY,
    JSON.stringify([{ name: "Warnings", query: "severity=warning" }]),
  );
  const { rerender } = render(
    <EventViews query="severity=warning" onApply={vi.fn()} />,
  );
  fireEvent.change(screen.getByLabelText("Saved event views"), {
    target: { value: "Warnings" },
  });
  rerender(<EventViews query="" onApply={vi.fn()} />);
  expect(
    (screen.getByLabelText("Saved event views") as HTMLSelectElement).value,
  ).toBe("");
});

it("handles unavailable browser storage without closing the save dialog", () => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Disabled");
  });
  render(<EventViews query="severity=warning" onApply={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Save view" }));
  fireEvent.change(screen.getByLabelText("View name"), {
    target: { value: "Warnings" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save filters" }));
  expect(screen.getByRole("alert").textContent).toContain("cannot save");
  expect(screen.getByRole("dialog")).toBeTruthy();
});

it("shows backup API errors and allows a retry", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({
        error: { message: "A backup is already running." },
      }),
    }),
  );
  render(<BackupPanel mode="live" />);
  fireEvent.click(screen.getByRole("button", { name: "Download backup" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).toContain("already running");
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Download backup",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
});
