import document from "./schema/responses.json";
type Schema = {
  $ref?: string;
  anyOf?: Schema[];
  const?: unknown;
  enum?: unknown[];
  type?: string;
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean;
  items?: Schema;
};
const definitions = document.$defs as Record<string, Schema>;
export function validateContract(value: unknown, name: string): boolean {
  const validate = (value: unknown, schema: Schema): boolean => {
    if (schema.$ref)
      return validate(value, definitions[schema.$ref.split("/").at(-1)!]);
    if (schema.anyOf) return schema.anyOf.some((s) => validate(value, s));
    if (schema.const !== undefined && value !== schema.const) return false;
    if (schema.enum && !schema.enum.includes(value)) return false;
    if (!schema.type) return true;
    if (schema.type === "null") return value === null;
    if (schema.type === "array")
      return (
        Array.isArray(value) && value.every((v) => validate(v, schema.items!))
      );
    if (schema.type === "object") {
      if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
      const v = value as Record<string, unknown>;
      return (
        (schema.required || []).every((k) => k in v) &&
        Object.keys(v).every((k) =>
          k in (schema.properties || {})
            ? validate(v[k], schema.properties![k])
            : schema.additionalProperties !== false,
        )
      );
    }
    if (schema.type === "integer")
      return typeof value === "number" && Number.isInteger(value);
    if (schema.type === "number")
      return typeof value === "number" && Number.isFinite(value);
    return typeof value === schema.type;
  };
  return !!definitions[name] && validate(value, definitions[name]);
}
export function responseContract(path: string, method = "GET") {
  const route = path.split("?")[0];
  if (
    (route === "/rfid/cards" && method === "POST") ||
    route.startsWith("/rfid/cards/")
  )
    return "card";
  if (route.startsWith("/devices/")) return "deviceDetail";
  return (
    {
      "/overview": "overview",
      "/devices": "devices",
      "/events": "events",
      "/events/summary": "summary",
      "/rfid/cards": "cards",
      "/rfid/activity": "activity",
      "/entry-monitor/stats": "entryStats",
      "/system": "system",
      "/health": "health",
    } as Record<string, string>
  )[route];
}
