// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  renderHook,
  act,
} from "@testing-library/react";
import { Stat, Pill, State, AuthBanner } from "./components";
import { useStream } from "./hooks";
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("dashboard states", () => {
  it("renders metric and textual severity", () => {
    render(
      <>
        <Stat label="Devices online" value="2 / 3" note="1 offline" />
        <Pill value="critical" />
      </>,
    );
    expect(screen.getByText("2 / 3")).toBeTruthy();
    expect(screen.getByText("Critical")).toBeTruthy();
  });
  it("provides retry, empty, and loading states", () => {
    const retry = vi.fn();
    const { rerender } = render(
      <State loading={false} error="Offline" retry={retry}>
        Data
      </State>,
    );
    fireEvent.click(screen.getByText("Try again"));
    expect(retry).toHaveBeenCalledOnce();
    rerender(
      <State loading error="" retry={retry}>
        Data
      </State>,
    );
    expect(screen.getByRole("status")).toBeTruthy();
    rerender(
      <State loading={false} empty error="" retry={retry}>
        Data
      </State>,
    );
    expect(screen.getByText("Nothing here yet")).toBeTruthy();
  });
  it("expires authorization without refetching", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-13T12:00:00Z"));
    render(
      <AuthBanner
        value={{
          active: true,
          card_uid: "ABCDEF12",
          card_label: "Dev",
          expires_at: "2026-10-13T12:00:02Z",
        }}
      />,
    );
    expect(screen.getByText(/Access authorized/)).toBeTruthy();
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByText("Access window closed")).toBeTruthy();
  });
  it("backs off and enables polling after three stream failures", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetch);
    const { result, unmount } = renderHook(() => useStream(true));
    await act(async () => {});
    expect(result.current.status).toBe("reconnecting");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.status).toBe("polling");
    const revision = result.current.revision;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(result.current.revision).toBeGreaterThan(revision);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
