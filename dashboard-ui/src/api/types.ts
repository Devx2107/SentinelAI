export type EventRecord = {
  id: number;
  timestamp: string;
  node_id: string;
  sensor: string;
  status: string;
  severity: string;
  confidence: number | null;
  message: string;
};
export type Device = {
  node_id: string;
  status: string;
  effective_status: "online" | "stale" | "offline";
  last_seen: string | null;
  seconds_since_seen: number | null;
  capabilities: string[];
  recent_events?: EventRecord[];
};
export type Card = {
  card_uid: string;
  label: string;
  active: boolean;
  notes: string | null;
  created_at: string;
  last_seen: string | null;
};
export type AuthWindow = {
  active: boolean;
  card_uid: string;
  card_label: string;
  expires_at: string;
} | null;
export type Overview = {
  hub: { node_id: string; uptime_seconds: number };
  counts: Record<string, number>;
  auth_window: AuthWindow;
  latest_events: EventRecord[];
};
export type EventsPage = {
  events: EventRecord[];
  next_cursor: number | null;
  total_matching: number;
};
export type Summary = {
  range: string;
  bucket: string;
  series: { t: string; info: number; warning: number; critical: number }[];
  by_sensor: { sensor: string; count: number }[];
};
export type EntryStats = {
  range: string;
  persons_confirmed: number;
  motion_no_person: number;
  avg_confidence_confirmed: number | null;
  confidence_histogram: { bucket: string; count: number }[];
  series: { t: string; person_confirmed: number; motion_no_person: number }[];
};
export type SystemInfo = {
  node_id: string;
  uptime_seconds: number;
  db: {
    path_basename: string;
    size_bytes: number;
    events: number;
    devices: number;
    cards: number;
  };
  mqtt_connected: boolean | null;
  stale_after_seconds: number;
  mode: "demo" | "live";
};
