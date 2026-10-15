import { useState, useEffect, useRef, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { authHeaders } from "./api/client";
import {
  addView,
  cleanQuery,
  parseViews,
  VIEW_KEY,
  type SavedView,
} from "./api/savedViews";
import type { Insights } from "./api/types";
import { useQuery } from "./hooks";
import { Icon, Modal, Panel, Pill, State } from "./components";

export function InsightsPanel({ revision }: { revision: number }) {
  const q = useQuery<Insights>("/insights", revision);
  const comparison = q.data?.comparison;
  return (
    <Panel
      title="Security insights"
      aside={<span className="muted">Signals to follow up</span>}
    >
      <State
        loading={!q.data && q.loading}
        error={q.error}
        hasData={!!q.data}
        retry={q.reload}
      >
        {q.data && (
          <>
            <div className="insight-metrics">
              <div>
                <strong>
                  {q.data.recent.warnings_1h + q.data.recent.critical_1h}
                </strong>
                <span>Warnings & critical · last hour</span>
              </div>
              <div>
                <strong>{comparison!.current.toLocaleString()}</strong>
                <span>
                  Events · last 24 hours{" "}
                  <b>
                    {comparison!.percent_change === null
                      ? "No previous baseline"
                      : `${comparison!.percent_change > 0 ? "+" : ""}${comparison!.percent_change}% vs previous 24h`}
                  </b>
                </span>
              </div>
              <div>
                <strong>{q.data.recent.cards_denied_1h}</strong>
                <span>Denied card scans · last hour</span>
              </div>
            </div>
            <div className="insight-alerts">
              {q.data.alerts.length ? (
                q.data.alerts.map((alert) => (
                  <Link
                    key={alert.id}
                    to={alert.href}
                    className="insight-alert"
                  >
                    <span className="insight-alert-copy">
                      <strong>{alert.title}</strong>
                      <small>{alert.detail}</small>
                    </span>
                    <Pill value={alert.severity} />
                    <Icon name="arrow" size={16} />
                  </Link>
                ))
              ) : (
                <div className="insight-clear">
                  <Icon name="shield" />
                  <span>
                    No recent warning events or device connection issues were
                    found.
                  </span>
                </div>
              )}
            </div>
            {!!q.data.top_devices.length && (
              <div className="insight-nodes">
                <span>Most active · 24h</span>
                {q.data.top_devices.map((node) => (
                  <Link
                    key={node.node_id}
                    to={"/events?node_id=" + encodeURIComponent(node.node_id)}
                  >
                    {node.node_id}
                    <strong>{node.events}</strong>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </State>
    </Panel>
  );
}

export function EventViews({
  query,
  onApply,
}: {
  query: string;
  onApply: (query: string) => void;
}) {
  const [views, setViews] = useState<SavedView[]>(() => {
    try {
      return parseViews(localStorage.getItem(VIEW_KEY));
    } catch {
      return [];
    }
  });
  const [selected, setSelected] = useState(""),
    [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    const view = views.find((v) => v.name === selected);
    if (view && view.query !== cleanQuery(query)) setSelected("");
  }, [query]);
  function persist(next: SavedView[]) {
    try {
      localStorage.setItem(VIEW_KEY, JSON.stringify(next));
      setViews(next);
      setError("");
      return true;
    } catch {
      setError(
        "This browser cannot save views. Enable local storage or use the URL to keep your filters.",
      );
      return false;
    }
  }
  function save(e: FormEvent) {
    e.preventDefault();
    try {
      const next = addView(views, name, query);
      if (persist(next)) {
        setOpen(false);
        setSelected(name.trim());
        setName("");
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function preset(kind: "hour" | "day" | "denied") {
    const params = new URLSearchParams();
    params.set(
      "since",
      new Date(
        Date.now() - (kind === "day" ? 86400000 : 3600000),
      ).toISOString(),
    );
    if (kind === "denied") {
      params.set("sensor", "rfid_auth");
      params.set("status", "card_denied");
    } else if (kind === "hour") params.set("severity", "warning,critical");
    setSelected("");
    onApply(params.toString());
  }
  return (
    <>
      <div className="event-views">
        <div className="preset-buttons">
          <button onClick={() => preset("hour")}>Recent warnings</button>
          <button onClick={() => preset("denied")}>Denied access</button>
          <button onClick={() => preset("day")}>Last 24 hours</button>
        </div>
        <div className="saved-view-controls">
          <select
            aria-label="Saved event views"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              const v = views.find((v) => v.name === e.target.value);
              if (v) onApply(v.query);
            }}
          >
            <option value="">Saved views ({views.length}/10)</option>
            {views.map((v) => (
              <option key={v.name} value={v.name}>
                {v.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => {
              setError("");
              setOpen(true);
            }}
          >
            Save view
          </button>
          {selected && (
            <button
              aria-label={"Remove saved view " + selected}
              onClick={() => {
                if (persist(views.filter((v) => v.name !== selected)))
                  setSelected("");
              }}
            >
              Remove
            </button>
          )}
        </div>
      </div>
      {error && !open && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {open && (
        <Modal title="Save event view" onClose={() => setOpen(false)}>
          <form onSubmit={save}>
            <label>
              View name
              <input
                autoFocus
                required
                maxLength={40}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Front door warnings"
              />
            </label>
            <p className="muted">
              Saves these filters in this browser. Date filters are stored as
              the selected dates. Credentials are never saved.
            </p>
            {error && (
              <p role="alert" className="inline-error">
                {error}
              </p>
            )}
            <footer>
              <button type="button" onClick={() => setOpen(false)}>
                Cancel
              </button>
              <button className="primary" disabled={!name.trim()}>
                Save filters
              </button>
            </footer>
          </form>
        </Modal>
      )}
    </>
  );
}

export function BackupPanel({ mode }: { mode: "demo" | "live" }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState("");
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function download() {
    setBusy(true);
    setError("");
    setSaved("");
    const controller = new AbortController();
    active.current = controller;
    try {
      const response = await fetch("/api/v1/backup", {
        headers: authHeaders(),
        signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 401)
          window.dispatchEvent(new Event("sentinel-unauthorized"));
        const failure = await response.json();
        throw new Error(
          failure.error?.message || "Backup failed. Retry shortly.",
        );
      }
      const blob = await response.blob();
      const filename =
        response.headers
          .get("Content-Disposition")
          ?.match(/filename="([A-Za-z0-9_.-]+)"/)?.[1] ||
        "sentinelai-backup.sqlite3";
      const url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setSaved(filename);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return (
    <Panel
      title="Database backup"
      aside={<span className="muted">Keep a recovery copy</span>}
    >
      <div className="backup-panel">
        <div>
          <strong>
            {mode === "demo"
              ? "Download a demo snapshot"
              : "Back up your hub data"}
          </strong>
          <p>
            Includes recorded events, device records, and trusted cards. The
            snapshot is consistent while the hub keeps running.
          </p>
          <small>
            {mode === "demo"
              ? "This contains synthetic demo data."
              : "Store the file privately; it includes card identifiers and notes."}
          </small>
        </div>
        <button className="primary" disabled={busy} onClick={download}>
          <Icon name="download" size={17} />
          {busy ? "Preparing snapshot…" : "Download backup"}
        </button>
      </div>
      {error && (
        <p className="inline-error backup-message" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="backup-message" role="status">
          Download started: {saved}
        </p>
      )}
    </Panel>
  );
}
