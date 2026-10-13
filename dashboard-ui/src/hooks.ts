import { useEffect, useState, useCallback } from "react";
import { api, authHeaders } from "./api/client";
import { validateContract } from "./api/contracts";
import type { EventRecord } from "./api/types";
export function useQuery<T>(path: string, refresh = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((v) => v + 1), []);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setError("");
    api<T>(path, { signal: abort.signal })
      .then(setData)
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [path, revision, refresh]);
  return { data, setData, error, loading, reload };
}
export function useNow() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}
export function useStream(enabled: boolean) {
  const [status, setStatus] = useState("connecting");
  const [revision, setRevision] = useState(0);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [critical, setCritical] = useState("");
  useEffect(() => {
    if (!enabled) return;
    setEvents([]);
    setCritical("");
    setStatus("connecting");
    let stopped = false,
      timer: ReturnType<typeof setTimeout>,
      poll: ReturnType<typeof setInterval> | undefined,
      last = "",
      failures = 0;
    const controller = new AbortController();
    const connect = async () => {
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
      try {
        const res = await fetch("/api/v1/stream", {
          headers: {
            ...authHeaders(),
            ...(last ? { "Last-Event-ID": last } : {}),
          },
          signal: controller.signal,
        });
        if (res.status === 401) {
          window.dispatchEvent(new Event("sentinel-unauthorized"));
          return;
        }
        if (!res.ok || !res.body) throw new Error("Disconnected");
        setStatus("live");
        if (poll) {
          clearInterval(poll);
          poll = undefined;
        }
        let buffer = "";
        reader = res.body.getReader();
        const decoder = new TextDecoder();
        while (!stopped) {
          const part = await reader.read();
          if (part.done) throw new Error("Disconnected");
          buffer += decoder
            .decode(part.value, { stream: true })
            .replaceAll("\r", "");
          let end;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            const block = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            let kind = "",
              data = "",
              id = "";
            for (const line of block.split("\n")) {
              if (line.startsWith("event:")) kind = line.slice(6).trim();
              if (line.startsWith("data:")) data += line.slice(5).trim();
              if (line.startsWith("id:")) id = line.slice(3).trim();
            }
            if (id) last = id;
            if (data) {
              failures = 0;
              const parsed = JSON.parse(data);
              if (kind === "event") {
                if (!validateContract(parsed, "event"))
                  throw new Error("Invalid event payload");
                setEvents((old) => [parsed, ...old].slice(0, 200));
                if (parsed.severity === "critical") setCritical(parsed.message);
              }
              if (kind !== "ping") setRevision((v) => v + 1);
            }
          }
        }
      } catch {
        if (stopped) return;
        failures++;
        setStatus(failures >= 3 ? "polling" : "reconnecting");
        if (failures >= 3 && !poll)
          poll = setInterval(() => setRevision((v) => v + 1), 10000);
        timer = setTimeout(
          connect,
          Math.min(30000, 1000 * 2 ** Math.min(failures - 1, 5)),
        );
      } finally {
        if (reader) {
          try {
            await reader.cancel();
          } catch {
            /* Connection already closed. */
          }
          reader.releaseLock();
        }
      }
    };
    connect();
    return () => {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
      if (poll) clearInterval(poll);
    };
  }, [enabled]);
  return { status, revision, events, critical };
}
