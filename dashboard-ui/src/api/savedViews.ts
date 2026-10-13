export type SavedView = { name: string; query: string };
export const VIEW_KEY = "sentinel-event-views-v1";
const allowed = new Set([
  "sensor",
  "node_id",
  "severity",
  "status",
  "since",
  "until",
  "q",
]);

export function cleanQuery(query: string) {
  const result = new URLSearchParams();
  for (const [key, value] of new URLSearchParams(query)) {
    if (allowed.has(key) && value) result.set(key, value);
  }
  return result.toString();
}

export function parseViews(raw: string | null): SavedView[] {
  try {
    const value: unknown = JSON.parse(raw || "[]");
    if (!Array.isArray(value)) return [];
    const seen = new Set<string>();
    return value
      .filter((v): v is SavedView => {
        if (
          !v ||
          typeof v.name !== "string" ||
          !v.name.trim() ||
          v.name.length > 40 ||
          typeof v.query !== "string" ||
          v.query.length > 2000 ||
          seen.has(v.name)
        )
          return false;
        seen.add(v.name);
        return true;
      })
      .slice(0, 10)
      .map((v) => ({ name: v.name, query: cleanQuery(v.query) }));
  } catch {
    return [];
  }
}

export function addView(
  views: SavedView[],
  name: string,
  query: string,
): SavedView[] {
  name = name.trim();
  if (!name || name.length > 40)
    throw new Error("Choose a view name with 1–40 characters.");
  if (query.length > 2000)
    throw new Error("These filters are too long to save.");
  const existing = views.find(
    (v) => v.name.toLowerCase() === name.toLowerCase(),
  );
  if (existing) throw new Error("A view with that name already exists.");
  if (views.length >= 10)
    throw new Error("You can save up to 10 views. Remove one first.");
  return [...views, { name, query: cleanQuery(query) }];
}
