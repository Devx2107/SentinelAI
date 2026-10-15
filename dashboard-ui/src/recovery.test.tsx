// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import * as client from "./api/client";
import { useQuery, useStream } from "./hooks";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function abortableFetch() {
  return vi.fn(
    (_url: string, options: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        options.signal!.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      }),
  );
}

it("bounds stalled requests and releases its timeout", async () => {
  vi.useFakeTimers();
  const fetch = abortableFetch();
  vi.stubGlobal("fetch", fetch);
  const request = client.api("/system");
  const outcome = expect(request).rejects.toThrow("took too long");
  await vi.advanceTimersByTimeAsync(15000);
  await outcome;
  expect(fetch.mock.calls[0][1].signal!.aborted).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

it("does not retry an uncertain write and explains how to recover", async () => {
  vi.useFakeTimers();
  const fetch = abortableFetch();
  vi.stubGlobal("fetch", fetch);
  const outcome = expect(
    client.api("/rfid/cards", { method: "POST", body: "{}" }),
  ).rejects.toThrow("may have completed; refresh");
  await vi.advanceTimersByTimeAsync(15000);
  await outcome;
  expect(fetch).toHaveBeenCalledOnce();
});

it("preserves caller cancellation and handles non-JSON authorization errors", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", abortableFetch());
  const controller = new AbortController();
  const outcome = expect(
    client.api("/system", { signal: controller.signal }),
  ).rejects.toMatchObject({ name: "AbortError" });
  controller.abort();
  await outcome;
  expect(vi.getTimerCount()).toBe(0);
  const unauthorized = vi.fn();
  window.addEventListener("sentinel-unauthorized", unauthorized);
  try {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html>Unauthorized</html>", { status: 401 }),
        ),
    );
    await expect(client.api("/system")).rejects.toThrow("HTTP 401");
    expect(unauthorized).toHaveBeenCalledOnce();
  } finally {
    window.removeEventListener("sentinel-unauthorized", unauthorized);
  }
});

it("ignores a stale query result even when the transport resolves after cancellation", async () => {
  let resolveOld!: (value: unknown) => void;
  vi.spyOn(client, "api")
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValueOnce("new result");
  const { result, rerender } = renderHook(
    ({ path }) => useQuery<string>(path),
    { initialProps: { path: "/old" } },
  );
  rerender({ path: "/new" });
  await act(async () => {});
  expect(result.current.data).toBe("new result");
  await act(async () => resolveOld("old result"));
  expect(result.current.data).toBe("new result");
});

it("retains data on refresh failure but clears it when the query changes", async () => {
  vi.spyOn(client, "api")
    .mockResolvedValueOnce("cached result")
    .mockRejectedValueOnce(new Error("offline"))
    .mockImplementationOnce(() => new Promise(() => {}));
  const { result, rerender } = renderHook(
    ({ path, refresh }) => useQuery<string>(path, refresh),
    { initialProps: { path: "/old", refresh: 0 } },
  );
  await act(async () => {});
  expect(result.current.data).toBe("cached result");
  rerender({ path: "/old", refresh: 1 });
  await act(async () => {});
  expect(result.current.data).toBe("cached result");
  expect(result.current.error).toBe("offline");
  rerender({ path: "/new", refresh: 1 });
  expect(result.current.data).toBeUndefined();
  expect(result.current.loading).toBe(true);
});

it("preserves cancellation while reading a response body", async () => {
  const controller = new AbortController();
  vi.stubGlobal(
    "fetch",
    vi.fn((_url, options) =>
      Promise.resolve({
        status: 200,
        ok: true,
        json: () =>
          new Promise((_resolve, reject) => {
            options.signal.addEventListener(
              "abort",
              () => reject(new DOMException("Aborted", "AbortError")),
              { once: true },
            );
          }),
      }),
    ),
  );
  const outcome = expect(
    client.api("/system", { signal: controller.signal }),
  ).rejects.toMatchObject({ name: "AbortError" });
  await Promise.resolve();
  controller.abort();
  await outcome;
});

function streamResponse(signal: AbortSignal, text = "", close = false) {
  let source!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      source = controller;
      if (text) controller.enqueue(new TextEncoder().encode(text));
      if (close) controller.close();
      else
        signal.addEventListener(
          "abort",
          () => controller.error(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
    },
  });
  return { response: new Response(body), source };
}

it("retains the last valid event cursor and falls back after malformed packets", async () => {
  vi.useFakeTimers();
  const event = {
    id: 10,
    timestamp: "2026-10-15T12:00:00Z",
    node_id: "hub",
    sensor: "entry_monitor",
    status: "person_confirmed",
    severity: "warning",
    confidence: 0.9,
    message: "Person",
  };
  let attempt = 0;
  const fetch = vi.fn((_url, options) => {
    const valid =
      attempt++ === 0
        ? `id: 10\nevent: event\ndata: ${JSON.stringify(event)}\n\n`
        : "";
    return Promise.resolve(
      streamResponse(
        options.signal,
        valid + 'id: 11\nevent: event\ndata: {"id":11}\n\n',
      ).response,
    );
  });
  vi.stubGlobal("fetch", fetch);
  const { result, unmount } = renderHook(() => useStream(true));
  await act(async () => {});
  expect(result.current.events).toEqual([event]);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
  expect(result.current.status).toBe("polling");
  expect(fetch.mock.calls[1][1].headers["Last-Event-ID"]).toBe("10");
  expect(fetch.mock.calls[2][1].headers["Last-Event-ID"]).toBe("10");
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it("aborts a silent stream and recovers when heartbeats return", async () => {
  vi.useFakeTimers();
  const signals: AbortSignal[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_url, options) => {
      signals.push(options.signal);
      return Promise.resolve(
        streamResponse(options.signal, "event: ping\ndata: {}\n\n").response,
      );
    }),
  );
  const { result, unmount } = renderHook(() => useStream(true));
  await act(async () => {});
  expect(result.current.status).toBe("live");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(45000);
  });
  expect(signals[0].aborted).toBe(true);
  expect(result.current.status).toBe("reconnecting");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(result.current.status).toBe("live");
  unmount();
  expect(signals[1].aborted).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

it("keeps polling until a reconnect delivers valid data", async () => {
  vi.useFakeTimers();
  let attempt = 0;
  let source!: ReadableStreamDefaultController<Uint8Array>;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url, options) => {
      const stream = streamResponse(options.signal, "", attempt++ < 3);
      source = stream.source;
      return Promise.resolve(stream.response);
    }),
  );
  const { result, unmount } = renderHook(() => useStream(true));
  await act(async () => {});
  await act(async () => {
    await vi.advanceTimersByTimeAsync(7000);
  });
  expect(result.current.status).toBe("polling");
  await act(async () => {
    source.enqueue(new TextEncoder().encode("event: ping\ndata: {}\n\n"));
  });
  expect(result.current.status).toBe("live");
  expect(vi.getTimerCount()).toBe(1); // Only the stream watchdog remains.
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});
