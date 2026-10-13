import { it, expect } from "vitest";
import fixtures from "./api/schema/fixtures.json";
import { validateContract } from "./api/contracts";
it("accepts the same Python-generated API fixtures for every response", () => {
  for (const [name, value] of Object.entries(fixtures))
    expect(validateContract(value, name), name).toBe(true);
});
it("rejects contract drift and numeric strings", () => {
  expect(
    validateContract({ ...fixtures.events, total_matching: "800" }, "events"),
  ).toBe(false);
  expect(
    validateContract({ ...fixtures.system, secret: "oops" }, "system"),
  ).toBe(false);
  expect(validateContract({ ...fixtures.card, active: 1 }, "card")).toBe(false);
});
