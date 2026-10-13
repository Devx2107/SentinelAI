import type { EventRecord } from "./types";
export const title = (s: string) =>
  s.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
export function relative(value: string | null, now = Date.now()) {
  if (!value) return "Not seen";
  const s = Math.max(0, Math.floor((now - Date.parse(value)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
export const absolute = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
export function mergeEvents(a: EventRecord[], b: EventRecord[]) {
  return [...new Map([...b, ...a].map((e) => [e.id, e])).values()].sort(
    (x, y) => y.id - x.id,
  );
}
export function matches(event: EventRecord, params: URLSearchParams) {
  for (const key of ["sensor", "node_id", "severity", "status"] as const) {
    const value = params.get(key);
    if (value && !value.split(",").includes(event[key])) return false;
  }
  const since = params.get("since"),
    until = params.get("until"),
    q = params.get("q");
  return (
    !(since && Date.parse(event.timestamp) < Date.parse(since)) &&
    !(until && Date.parse(event.timestamp) >= Date.parse(until)) &&
    (!q || event.message.toLowerCase().includes(q.toLowerCase()))
  );
}
export function csvCell(value: unknown) {
  let text = String(value ?? "");
  if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function toCSV(events: EventRecord[]) {
  const keys = [
    "id",
    "timestamp",
    "node_id",
    "sensor",
    "status",
    "severity",
    "confidence",
    "message",
  ] as const;
  return [
    keys.join(","),
    ...events
      .slice(0, 1000)
      .map((e) => keys.map((k) => csvCell(e[k])).join(",")),
  ].join("\r\n");
}
export const validUID = (s: string) =>
  /^[0-9A-F]{8,20}$/.test(s.trim().toUpperCase());
