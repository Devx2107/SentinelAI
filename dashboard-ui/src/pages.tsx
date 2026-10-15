import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "./api/client";
import {
  absolute,
  matches,
  mergeEvents,
  title,
  toCSV,
  validUID,
} from "./api/helpers";
import type {
  Card,
  Device,
  EntryStats,
  EventRecord,
  EventsPage,
  Overview,
  Summary,
  SystemInfo,
} from "./api/types";
import { useQuery } from "./hooks";
import { InsightsPanel, EventViews, BackupPanel } from "./featurePanels";
import { dashboardVersion } from "./version";
import {
  AuthBanner,
  Chart,
  DeviceCard,
  EventsList,
  Icon,
  Modal,
  Panel,
  Pill,
  State,
  Stat,
  Time,
} from "./components";
type Live = { revision: number; events: EventRecord[]; status?: string };

export function OverviewPage({ revision }: Live) {
  const overview = useQuery<Overview>("/overview", revision),
    devices = useQuery<{ devices: Device[] }>("/devices", revision),
    summary = useQuery<Summary>("/events/summary", revision);
  const d = overview.data,
    c = d?.counts;
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow">YOUR SPACE. IN SIGHT.</div>
        <h1>
          Control room<span>.</span>
        </h1>
        <p>A clear view of your home, from the front door to every edge.</p>
      </div>
      <State
        loading={!d && overview.loading}
        error={overview.error}
        hasData={!!overview.data}
        retry={overview.reload}
      >
        {d && (
          <>
            <div
              className={
                "status-banner " + (c!.critical_24h ? "attention" : "")
              }
            >
              <span className="status-mark">
                <Icon name="shield" size={25} />
              </span>
              <div>
                <strong>
                  {c!.critical_24h
                    ? "Activity needs your attention"
                    : c!.warnings_24h
                      ? "Your perimeter, in focus"
                      : "All clear. You’re in the loop."}
                </strong>
                <p>
                  {c!.warnings_24h} warnings and {c!.critical_24h} critical
                  events recorded in the last 24 hours.
                </p>
              </div>
              <Link to="/events?severity=warning,critical">
                Review activity <Icon name="arrow" size={17} />
              </Link>
            </div>
            <div className="stats-grid">
              <Stat
                label="Devices online"
                value={`${c!.devices_online} / ${c!.devices_total}`}
                note={`${c!.devices_stale} stale · ${c!.devices_offline} offline`}
                icon="devices"
              />
              <Stat
                label="Events · 24 hours"
                value={c!.events_24h}
                note="Recorded in the last 24 hours"
                icon="events"
              />
              <Stat
                label="People detected"
                value={c!.persons_confirmed_24h}
                note="Camera-confirmed detections"
                icon="entry"
              />
              <Stat
                label="Access denied"
                value={c!.cards_denied_24h}
                note="Unrecognized or disabled cards"
                icon="access"
              />
            </div>
            <InsightsPanel revision={revision} />
            <div className="overview-grid">
              <Panel
                title="Activity at a glance"
                aside={<span className="muted">Last 24 hours</span>}
              >
                <State
                  loading={!summary.data && summary.loading}
                  error={summary.error}
                  hasData={!!summary.data}
                  retry={summary.reload}
                >
                  {summary.data && (
                    <Chart
                      rows={summary.data.series}
                      keys={["info", "warning", "critical"]}
                      labels={["Routine", "Warning", "Critical"]}
                      name="24-hour event severity"
                    />
                  )}
                </State>
              </Panel>
              <Panel
                title="Your network"
                aside={<Link to="/devices">All devices ↗</Link>}
              >
                <State
                  loading={!devices.data && devices.loading}
                  error={devices.error}
                  hasData={!!devices.data}
                  retry={devices.reload}
                  empty={devices.data?.devices.length === 0}
                >
                  <div className="network-list">
                    {devices.data?.devices.map((device) => (
                      <Link
                        key={device.node_id}
                        to={"/devices/" + device.node_id}
                      >
                        <span className="device-icon">
                          <Icon name="devices" />
                        </span>
                        <span>
                          <strong>{device.node_id}</strong>
                          <small>
                            {device.node_id === "hub"
                              ? "Central hub"
                              : "Edge node"}
                          </small>
                        </span>
                        <Pill value={device.effective_status} />
                      </Link>
                    ))}
                  </div>
                  <div className="network-note">
                    Connected through your local network.
                    <br />
                    Device status is based on the latest heartbeat.
                  </div>
                </State>
              </Panel>
            </div>
            <AuthBanner value={d.auth_window} />
            <Panel
              title="Latest activity"
              aside={
                <Link to="/events">
                  View all events <span aria-hidden="true">↗</span>
                </Link>
              }
            >
              <State
                loading={false}
                error=""
                retry={() => {}}
                empty={!d.latest_events.length}
              >
                <EventsList events={d.latest_events} />
              </State>
            </Panel>
          </>
        )}
      </State>
    </>
  );
}

export function EventsPageView({ revision, events: incoming, status }: Live) {
  const [params, setParams] = useSearchParams();
  const [live, setLive] = useState(true);
  const [rows, setRows] = useState<EventRecord[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [moreError, setMoreError] = useState("");
  const [fetching, setFetching] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);
  const version = useRef("");
  const query = params.toString();
  version.current = query;
  const result = useQuery<EventsPage>("/events?limit=50&" + query);
  useEffect(() => {
    setRows([]);
    setCursor(null);
    setMoreError("");
  }, [query]);
  useEffect(() => {
    if (result.data) {
      setRows(result.data.events);
      setCursor(result.data.next_cursor);
    }
  }, [result.data]);
  useEffect(() => {
    if (live && incoming.length)
      setRows((old) =>
        mergeEvents(
          incoming.filter((e) => matches(e, params)),
          old,
        ),
      );
  }, [incoming, live, query]);
  useEffect(() => {
    if (live && revision && status === "polling") result.reload();
  }, [revision, status]);
  const load = async () => {
    if (!cursor || fetching) return;
    const key = query;
    setFetching(true);
    setMoreError("");
    try {
      const page = await api<EventsPage>(
        `/events?limit=50&${query}&cursor=${cursor}`,
      );
      if (version.current === key) {
        setRows((old) => mergeEvents(old, page.events));
        setCursor(page.next_cursor);
      }
    } catch (e) {
      if (version.current === key) setMoreError((e as Error).message);
    } finally {
      setFetching(false);
    }
  };
  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && cursor && !fetching && !moreError)
        void load();
    });
    if (sentinel.current) observer.observe(sentinel.current);
    return () => observer.disconnect();
  }, [cursor, fetching, query, moreError]);
  const filter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.delete("cursor");
    value ? next.set(key, value) : next.delete(key);
    setParams(next);
  };
  const exportCSV = () => {
    const url = URL.createObjectURL(
      new Blob(["\ufeff" + toCSV(rows)], { type: "text/csv;charset=utf-8;" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "sentinel-events.csv";
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <Heading
        eyebrow="THE FULL PICTURE"
        title="Event timeline"
        description="Every signal, in sequence. Find what matters."
      />
      <div className="toolbar">
        <label className="search">
          <Icon name="search" />
          <input
            aria-label="Search event messages"
            placeholder="Search activity…"
            value={params.get("q") || ""}
            onChange={(e) => filter("q", e.target.value)}
          />
        </label>
        <label className="toggle">
          <input
            type="checkbox"
            checked={live}
            onChange={(e) => setLive(e.target.checked)}
          />{" "}
          Live updates
        </label>
        <button onClick={exportCSV} disabled={!rows.length || result.loading}>
          <Icon name="download" size={17} />
          Export CSV
        </button>
      </div>
      <div className="filter-bar">
        <label>
          Sensor
          <select
            aria-label="Sensor"
            value={params.get("sensor") || ""}
            onChange={(e) => filter("sensor", e.target.value)}
          >
            <option value="">All sensors</option>
            <option value="entry_monitor">Entry monitor</option>
            <option value="rfid_auth">RFID access</option>
          </select>
        </label>
        <label>
          Device
          <input
            placeholder="Any node"
            value={params.get("node_id") || ""}
            onChange={(e) => filter("node_id", e.target.value)}
          />
        </label>
        <label>
          Severity
          <select
            aria-label="Severity"
            value={params.get("severity") || ""}
            onChange={(e) => filter("severity", e.target.value)}
          >
            <option value="">All severities</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
            <option value="warning,critical">Warning + critical</option>
          </select>
        </label>
        <label>
          Status
          <select
            aria-label="Status"
            value={params.get("status") || ""}
            onChange={(e) => filter("status", e.target.value)}
          >
            <option value="">All statuses</option>
            {[
              "person_confirmed",
              "motion_no_person",
              "person_confirmed_authenticated",
              "motion_authenticated",
              "card_authorized",
              "card_denied",
            ].map((s) => (
              <option key={s} value={s}>
                {title(s)}
              </option>
            ))}
          </select>
        </label>
        {["since", "until"].map((key) => (
          <label key={key}>
            {key === "since" ? "From" : "Until"}
            <input
              type="datetime-local"
              aria-label={key}
              value={params.get(key) ? localDate(params.get(key)!) : ""}
              onChange={(e) =>
                filter(
                  key,
                  e.target.value ? new Date(e.target.value).toISOString() : "",
                )
              }
            />
          </label>
        ))}
        <button className="text-button" onClick={() => setParams({})}>
          Reset
        </button>
      </div>
      <EventViews
        query={query}
        onApply={(value) => setParams(new URLSearchParams(value))}
      />
      <Panel
        title="Recorded events"
        aside={
          <span className="muted">
            {result.data?.total_matching ?? "—"} matching
          </span>
        }
      >
        <State
          loading={result.loading && !result.data}
          error={result.error}
          hasData={!!result.data}
          retry={result.reload}
          empty={!rows.length}
        >
          <EventsList events={rows} />
        </State>
        <div className="pagination" ref={sentinel}>
          {moreError && <p role="alert">{moreError}</p>}
          {cursor && (
            <button onClick={load} disabled={fetching}>
              {fetching ? "Loading…" : "Load more events"}
            </button>
          )}
          <small>
            CSV exports loaded rows only ({Math.min(rows.length, 1000)}).{" "}
            {cursor ? "More results are available. " : ""}
            {rows.length > 1000 ? "Export limited to 1,000 rows." : ""}
          </small>
        </div>
      </Panel>
    </>
  );
}
function localDate(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function Heading({
  eyebrow,
  title: heading,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="page-heading">
      <div className="eyebrow">{eyebrow}</div>
      <h1>
        {heading}
        <span>.</span>
      </h1>
      <p>{description}</p>
    </div>
  );
}

export function DevicesPage({ revision }: Live) {
  const q = useQuery<{ devices: Device[] }>("/devices", revision);
  return (
    <>
      <Heading
        eyebrow="ONE CONNECTED NETWORK"
        title="Your devices"
        description="A home-wide view of every hub and edge node."
      />
      <State
        loading={!q.data && q.loading}
        error={q.error}
        hasData={!!q.data}
        retry={q.reload}
        empty={!q.data?.devices.length}
      >
        <div className="devices-grid">
          {q.data?.devices.map((d) => (
            <DeviceCard device={d} key={d.node_id} />
          ))}
        </div>
        <div className="info-note">
          <Icon name="devices" />
          <p>
            Online devices become <strong>stale</strong> when heartbeats stop.
            Offline status is reported by the node or broker.
          </p>
        </div>
      </State>
    </>
  );
}
export function DeviceDetail({ revision }: Live) {
  const { id } = useParams();
  const q = useQuery<Device>(
    "/devices/" + encodeURIComponent(id || ""),
    revision,
  );
  return (
    <>
      <Link className="back" to="/devices">
        ← All devices
      </Link>
      <Heading
        eyebrow="DEVICE DETAILS"
        title={id || "Device"}
        description="Connection status, capabilities, and recent activity."
      />
      <State
        loading={!q.data && q.loading}
        error={q.error}
        hasData={!!q.data}
        retry={q.reload}
      >
        {q.data && (
          <>
            <div className="detail-summary">
              <Pill value={q.data.effective_status} />
              <span>
                Last seen <Time value={q.data.last_seen} />
              </span>
              <div className="chips">
                {q.data.capabilities.map((c) => (
                  <span key={c}>{c}</span>
                ))}
              </div>
            </div>
            <Panel title="Recent device activity">
              <State
                loading={false}
                error=""
                retry={() => {}}
                empty={!q.data.recent_events?.length}
              >
                <EventsList events={q.data.recent_events || []} />
              </State>
            </Panel>
          </>
        )}
      </State>
    </>
  );
}

export function AccessPage({ revision }: Live) {
  const cards = useQuery<{ cards: Card[] }>("/rfid/cards", revision),
    activity = useQuery<{ events: EventRecord[] }>(
      "/rfid/activity?limit=15",
      revision,
    ),
    overview = useQuery<Overview>("/overview", revision);
  const [editing, setEditing] = useState<Card | "new" | null>(null),
    [toggle, setToggle] = useState<Card | null>(null),
    [saving, setSaving] = useState(false),
    [error, setError] = useState("");
  async function changeActive() {
    if (!toggle) return;
    const before = cards.data;
    setSaving(true);
    setError("");
    cards.setData((old) =>
      old
        ? {
            cards: old.cards.map((c) =>
              c.card_uid === toggle.card_uid ? { ...c, active: !c.active } : c,
            ),
          }
        : old,
    );
    try {
      await api("/rfid/cards/" + toggle.card_uid, {
        method: "PATCH",
        body: JSON.stringify({ active: !toggle.active }),
      });
      setToggle(null);
      cards.reload();
    } catch (e) {
      cards.setData(before);
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <div className="heading-with-action">
        <Heading
          eyebrow="KNOW WHO COMES HOME"
          title="Access control"
          description="Manage trusted cards and follow every authentication."
        />
        <button
          className="primary"
          onClick={() => {
            setError("");
            setEditing("new");
          }}
        >
          <Icon name="plus" size={17} />
          Add card
        </button>
      </div>
      {overview.error ? (
        <div className="inline-error" role="alert">
          Access state unavailable.{" "}
          <button onClick={overview.reload}>Retry</button>
        </div>
      ) : (
        <AuthBanner value={overview.data?.auth_window || null} />
      )}
      <Panel
        title="Trusted cards"
        aside={
          <span className="muted">
            {cards.data?.cards.filter((c) => c.active).length ?? 0} enabled
          </span>
        }
      >
        <State
          loading={!cards.data && cards.loading}
          error={cards.error}
          hasData={!!cards.data}
          retry={cards.reload}
          empty={!cards.data?.cards.length}
        >
          <div className="table-scroll">
            <table className="cards-table">
              <thead>
                <tr>
                  <th>Card / owner</th>
                  <th>UID</th>
                  <th>Status</th>
                  <th>Last used</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {cards.data?.cards.map((c) => (
                  <tr key={c.card_uid}>
                    <td>
                      <strong>{c.label}</strong>
                      <small>{c.notes || "No notes"}</small>
                    </td>
                    <td className="mono">{c.card_uid}</td>
                    <td>
                      <Pill value={c.active ? "enabled" : "disabled"} />
                    </td>
                    <td>
                      <Time value={c.last_seen} />
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          onClick={() => setEditing(c)}
                          aria-label={`Edit ${c.label}`}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => {
                            setError("");
                            setToggle(c);
                          }}
                          aria-label={`${c.active ? "Disable" : "Enable"} ${c.label}`}
                        >
                          {c.active ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </State>
      </Panel>
      <Panel title="Recent access activity">
        <State
          loading={!activity.data && activity.loading}
          error={activity.error}
          hasData={!!activity.data}
          retry={activity.reload}
          empty={!activity.data?.events.length}
        >
          <EventsList events={activity.data?.events || []} />
        </State>
      </Panel>
      {editing && (
        <CardEditor
          card={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            cards.reload();
          }}
        />
      )}
      {toggle && (
        <Modal
          title={`${toggle.active ? "Disable" : "Enable"} ${toggle.label}?`}
          onClose={() => {
            if (!saving) setToggle(null);
          }}
        >
          <p>
            {toggle.active
              ? "This card will no longer authorize access. You can enable it again later."
              : "This card will be allowed to authorize access again."}
          </p>
          {error && (
            <p role="alert" className="inline-error">
              {error}
            </p>
          )}
          <footer>
            <button onClick={() => setToggle(null)} disabled={saving}>
              Cancel
            </button>
            <button
              className="primary"
              onClick={changeActive}
              disabled={saving}
            >
              {saving ? "Saving…" : "Confirm"}
            </button>
          </footer>
        </Modal>
      )}
    </>
  );
}
function CardEditor({
  card,
  onClose,
  onSaved,
}: {
  card: Card | "new";
  onClose: () => void;
  onSaved: () => void;
}) {
  const [uid, setUID] = useState(card === "new" ? "" : card.card_uid),
    [label, setLabel] = useState(card === "new" ? "" : card.label),
    [notes, setNotes] = useState(card === "new" ? "" : card.notes || ""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!validUID(uid)) {
      setError("Use 8–20 hexadecimal characters (0–9, A–F).");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await api("/rfid/cards" + (card === "new" ? "" : "/" + card.card_uid), {
        method: card === "new" ? "POST" : "PATCH",
        body: JSON.stringify({
          ...(card === "new" ? { card_uid: uid } : {}),
          label: label.trim(),
          notes,
        }),
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      title={card === "new" ? "Add a trusted card" : "Edit trusted card"}
      onClose={() => {
        if (!saving) onClose();
      }}
    >
      <form onSubmit={submit}>
        <label>
          Card UID
          <input
            autoFocus={card === "new"}
            disabled={card !== "new"}
            required
            value={uid}
            onChange={(e) => setUID(e.target.value.toUpperCase())}
            maxLength={20}
            placeholder="04A1B2C3"
            aria-invalid={!!uid && !validUID(uid)}
          />
          <small>8–20 hexadecimal characters. No spaces or separators.</small>
        </label>
        <label>
          Owner / label
          <input
            autoFocus={card !== "new"}
            required
            maxLength={40}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Front door key"
          />
        </label>
        <label>
          Notes
          <textarea
            maxLength={2000}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional details about this card"
          />
        </label>
        {error && (
          <p role="alert" className="inline-error">
            {error}
          </p>
        )}
        <footer>
          <button type="button" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            className="primary"
            disabled={saving || !label.trim() || !validUID(uid)}
          >
            {saving ? "Saving…" : "Save card"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}

export function EntryPage({ revision }: Live) {
  const [range, setRange] = useState("24h");
  const q = useQuery<EntryStats>(
    "/entry-monitor/stats?range=" + range,
    revision,
  );
  return (
    <>
      <div className="heading-with-action">
        <Heading
          eyebrow="MOTION, WITH CONTEXT"
          title="Entry monitor"
          description="Understand what the camera confirms after each motion trigger."
        />
        <div className="segmented" aria-label="Analytics range">
          {["24h", "7d"].map((r) => (
            <button
              key={r}
              aria-pressed={range === r}
              onClick={() => setRange(r)}
            >
              {r === "24h" ? "24 hours" : "7 days"}
            </button>
          ))}
        </div>
      </div>
      <State
        loading={!q.data && q.loading}
        error={q.error}
        hasData={!!q.data}
        retry={q.reload}
      >
        {q.data && (
          <>
            <div className="stats-grid three">
              <Stat
                label="People confirmed"
                value={q.data.persons_confirmed}
                note="Person detections in this range"
                icon="entry"
              />
              <Stat
                label="Motion only"
                value={q.data.motion_no_person}
                note="No person confirmed"
                icon="events"
              />
              <Stat
                label="Average confidence"
                value={
                  q.data.avg_confidence_confirmed === null
                    ? "—"
                    : `${Math.round(q.data.avg_confidence_confirmed * 100)}%`
                }
                note="Confidence, not model accuracy"
                icon="shield"
              />
            </div>
            <Panel title="Motion & person detection">
              <Chart
                rows={q.data.series}
                keys={["motion_no_person", "person_confirmed"]}
                labels={["Motion only", "Person confirmed"]}
                name="Entry detections over time"
              />
            </Panel>
            <Panel
              title="Detection confidence"
              aside={<span className="muted">Confirmed people only</span>}
            >
              <Chart
                rows={q.data.confidence_histogram}
                keys={["count"]}
                labels={["Detections"]}
                name="Confidence distribution"
              />
            </Panel>
          </>
        )}
      </State>
    </>
  );
}
export function SystemPage({ revision }: Live) {
  const q = useQuery<SystemInfo>("/system", revision);
  return (
    <>
      <Heading
        eyebrow="BEHIND THE SCENES"
        title="System health"
        description="Know what is running, connected, and ready."
      />
      <State
        loading={!q.data && q.loading}
        error={q.error}
        hasData={!!q.data}
        retry={q.reload}
      >
        {q.data && (
          <>
            <div className="status-banner">
              <span className="status-mark">
                <Icon name="system" size={25} />
              </span>
              <div>
                <strong>
                  {q.data.mode === "demo"
                    ? "Demo environment is running"
                    : "Live hub is running"}
                </strong>
                <p>
                  {q.data.mode === "demo"
                    ? "Synthetic data · no hardware connection required"
                    : "Verify connected hardware using the readiness checks below."}
                </p>
              </div>
              <Pill value={q.data.mode} />
            </div>
            <div className="stats-grid three">
              <Stat
                label="Hub uptime"
                value={`${Math.floor(q.data.uptime_seconds / 3600)}h ${Math.floor((q.data.uptime_seconds % 3600) / 60)}m`}
                note={q.data.node_id}
                icon="system"
              />
              <Stat
                label="Stored events"
                value={q.data.db.events.toLocaleString()}
                note={`${q.data.db.devices} devices · ${q.data.db.cards} cards`}
                icon="events"
              />
              <Stat
                label="Database size"
                value={`${(q.data.db.size_bytes / 1024).toFixed(0)} KB`}
                note={q.data.db.path_basename}
                icon="devices"
              />
            </div>
            <Panel title="Connection & configuration">
              <dl className="settings-list">
                <div>
                  <dt>MQTT broker</dt>
                  <dd>
                    {q.data.mqtt_connected === null
                      ? "Not available in demo mode"
                      : q.data.mqtt_connected
                        ? "Connected"
                        : "Disconnected"}
                  </dd>
                </div>
                <div>
                  <dt>Stale device threshold</dt>
                  <dd>{q.data.stale_after_seconds} seconds</dd>
                </div>
                <div>
                  <dt>Dashboard version</dt>
                  <dd>{dashboardVersion}</dd>
                </div>
                <div>
                  <dt>Data transport</dt>
                  <dd>SQLite + resumable server-sent events</dd>
                </div>
                <div>
                  <dt>Time display</dt>
                  <dd>{Intl.DateTimeFormat().resolvedOptions().timeZone}</dd>
                </div>
                <div>
                  <dt>Legacy dashboard</dt>
                  <dd>
                    <a href="/dashboard">Open dashboard v1 ↗</a>
                  </dd>
                </div>
              </dl>
            </Panel>
            <Readiness revision={revision} />
            <BackupPanel mode={q.data.mode} />
          </>
        )}
      </State>
    </>
  );
}
function Readiness({ revision }: Pick<Live, "revision">) {
  const q = useQuery<{
    checks: { name: string; ok: boolean; detail: string }[];
  }>("/readiness", revision);
  return (
    <Panel title="Startup readiness">
      <State
        loading={!q.data && q.loading}
        error={q.error}
        hasData={!!q.data}
        retry={q.reload}
      >
        <dl className="settings-list">
          {q.data?.checks.map((c) => (
            <div key={c.name}>
              <dt>
                {c.name}
                <small>{c.detail}</small>
              </dt>
              <dd>
                <Pill value={c.ok ? "ready" : "pending"} />
              </dd>
            </div>
          ))}
        </dl>
      </State>
    </Panel>
  );
}
