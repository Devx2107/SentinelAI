import { describe, it, expect } from "vitest";
import { csvCell, toCSV, mergeEvents, matches, validUID } from "./api/helpers";
import type { EventRecord } from "./api/types";
const event: EventRecord = {
  id: 1,
  timestamp: "2026-10-13T12:00:00Z",
  node_id: "hub",
  sensor: "entry_monitor",
  status: "person_confirmed",
  severity: "warning",
  confidence: 0.9,
  message: 'Person, "front door"\nline two',
};
describe("event and card helpers", () => {
  it("deduplicates paged and streamed events in descending order", () => {
    expect(
      mergeEvents([event], [event, { ...event, id: 2 }]).map((e) => e.id),
    ).toEqual([2, 1]);
  });
  it("matches filters including half-open date ranges", () => {
    expect(
      matches(event, new URLSearchParams("severity=critical,warning&q=FRONT")),
    ).toBe(true);
    expect(
      matches(event, new URLSearchParams("until=2026-10-13T12:00:00Z")),
    ).toBe(false);
    expect(matches(event, new URLSearchParams("sensor=rfid_auth"))).toBe(false);
  });
  it("escapes CSV and neutralizes formula prefixes", () => {
    expect(csvCell("=SUM(A1)")).toBe('"\'=SUM(A1)"');
    expect(csvCell(" @x")).toBe('"\' @x"');
    expect(toCSV([event])).toContain('"Person, ""front door""\nline two"');
  });
  it("limits export to 1000 rows", () =>
    expect(
      toCSV(Array(1100).fill({ ...event, message: "ok" })).split("\r\n"),
    ).toHaveLength(1001));
  it("uses backend-compatible UID rules", () => {
    expect(validUID(" abcdef12 ")).toBe(true);
    expect(validUID("04:AB:12:CD")).toBe(false);
    expect(validUID("abc")).toBe(false);
    expect(validUID("G".repeat(8))).toBe(false);
  });
});
