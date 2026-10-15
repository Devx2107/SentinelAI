import { useEffect, useRef, useId, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { AuthWindow, Device, EventRecord } from "./api/types";
import { absolute, relative, title } from "./api/helpers";
import { useNow } from "./hooks";

const paths: Record<string, string> = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  events: "M4 5h16M4 12h16M4 19h16",
  devices: "M3 4h18v12H3z M8 21h8M12 16v5",
  access: "M7 10V7a5 5 0 0110 0v3 M5 10h14v11H5z M12 14v3",
  entry: "M3 18V6l7-3v18l-7-3z M10 6h9v12h-9M7 12h.01",
  system:
    "M12 8a4 4 0 100 8 4 4 0 000-8z M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10l2 2M5 19l2-2M17 7l2-2",
  shield: "M12 2l8 3v6c0 5-8 11-8 11S4 16 4 11V5l8-3z M8 12l3 3 5-6",
  arrow: "M5 12h14m-5-5l5 5-5 5",
  logout: "M9 4H4v16h5m5-13l5 5-5 5M8 12h11",
  plus: "M12 5v14M5 12h14",
  search: "M10 3a7 7 0 100 14 7 7 0 000-14z M15 15l6 6",
  download: "M12 3v12m-5-5l5 5 5-5M4 17v4h16v-4",
};
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name] || paths.shield} />
    </svg>
  );
}
export function Pill({ value }: { value: string }) {
  return (
    <span className={`pill ${value}`}>
      <span aria-hidden="true">
        {value === "critical" ? "!" : value === "warning" ? "△" : "●"}
      </span>
      {title(value)}
    </span>
  );
}
export function Stat({
  label,
  value,
  note,
  icon = "overview",
}: {
  label: string;
  value: string | number;
  note: string;
  icon?: string;
}) {
  return (
    <article className="stat">
      <div>
        <span>{label}</span>
        <Icon name={icon} />
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}
export function Panel({
  title: heading,
  aside,
  children,
  className = "",
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <header className="panel-head">
        <h2>{heading}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}
export function State({
  loading,
  error,
  retry,
  empty,
  children,
  hasData = false,
}: {
  loading: boolean;
  error: string;
  retry: () => void;
  empty?: boolean;
  children: ReactNode;
  hasData?: boolean;
}) {
  if (error && !hasData)
    return (
      <div className="state" role="alert">
        <strong>Couldn’t load this view</strong>
        <p>{error}</p>
        <button onClick={retry}>Try again</button>
      </div>
    );
  if (loading)
    return (
      <div className="skeleton" role="status" aria-label="Loading data">
        <span />
        <span />
        <span />
      </div>
    );
  if (empty && !error)
    return (
      <div className="state">
        <Icon name="events" size={30} />
        <strong>Nothing here yet</strong>
        <p>New activity will appear here when it’s recorded.</p>
      </div>
    );
  return (
    <>
      {error && hasData && (
        <div className="connection-notice" role="alert">
          <strong>Couldn’t refresh. Showing last loaded data.</strong>
          <p>{error}</p>
          <button onClick={retry}>Try again</button>
        </div>
      )}
      {children}
    </>
  );
}
export function Time({ value }: { value: string | null }) {
  const now = useNow();
  return value ? (
    <time dateTime={value} title={absolute(value)}>
      {relative(value, now)}
    </time>
  ) : (
    <span>Not seen</span>
  );
}
export function EventsList({ events }: { events: EventRecord[] }) {
  return (
    <div className="event-list">
      {events.map((event) => (
        <details className="event-row" key={event.id}>
          <summary>
            <span className={"event-symbol " + event.severity}>
              <Icon name={event.sensor === "rfid_auth" ? "access" : "entry"} />
            </span>
            <span className="event-main">
              <strong>{title(event.status)}</strong>
              <small>
                {title(event.sensor)} <span>·</span> {event.node_id}
              </small>
            </span>
            <Pill value={event.severity} />
            <Time value={event.timestamp} />
            <span className="expand" aria-hidden="true">
              ⌄
            </span>
          </summary>
          <div className="event-detail">
            <p>{event.message}</p>
            <span>
              {absolute(event.timestamp)} · Event #{event.id}
            </span>
            {event.confidence !== null && (
              <span>
                Detection confidence: {Math.round(event.confidence * 100)}%
              </span>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}
export function DeviceCard({ device }: { device: Device }) {
  return (
    <Link
      to={"/devices/" + encodeURIComponent(device.node_id)}
      className="device-card"
    >
      <div className="device-top">
        <span className="device-icon">
          <Icon name="devices" size={25} />
        </span>
        <Pill value={device.effective_status} />
      </div>
      <h3>{device.node_id}</h3>
      <p>
        {device.node_id === "hub" ? "Central hub" : "Edge node"} ·{" "}
        <Time value={device.last_seen} />
      </p>
      <div className="chips">
        {device.capabilities.map((c) => (
          <span key={c}>{c}</span>
        ))}
      </div>
      <div className="device-foot">
        View device <Icon name="arrow" size={16} />
      </div>
    </Link>
  );
}
export function AuthBanner({ value }: { value: AuthWindow }) {
  const now = useNow();
  const seconds = value
    ? Math.max(0, Math.ceil((Date.parse(value.expires_at) - now) / 1000))
    : 0;
  return (
    <div className={"auth-banner " + (seconds ? "active" : "")}>
      <div className="ring">
        <svg viewBox="0 0 44 44" aria-hidden="true">
          <circle cx="22" cy="22" r="18" />
          <circle
            cx="22"
            cy="22"
            r="18"
            strokeDasharray={`${Math.min(1, seconds / 30) * 113} 113`}
          />
        </svg>
        <span>{seconds ? seconds : <Icon name="access" size={17} />}</span>
      </div>
      <div>
        <strong>
          {seconds
            ? `Access authorized · ${value?.card_label}`
            : "Access window closed"}
        </strong>
        <p>
          {seconds
            ? `Authorization expires in ${seconds}s`
            : "A recognized card opens a temporary authorization window."}
        </p>
      </div>
      <span className="auth-label">RFID ACCESS</span>
    </div>
  );
}
export function Chart({
  rows,
  keys,
  labels,
  name,
}: {
  rows: Record<string, number | string>[];
  keys: string[];
  labels: string[];
  name: string;
}) {
  const max = Math.max(
    1,
    ...rows.map((r) => keys.reduce((n, k) => n + Number(r[k] || 0), 0)),
  );
  return (
    <div className="chart">
      <div className="chart-legend">
        {labels.map((label, i) => (
          <span key={label}>
            <i className={"legend-" + i} />
            {label}
          </span>
        ))}
      </div>
      <div
        className="chart-plot"
        role="img"
        aria-label={`${name}. ${rows.length} time buckets. Data table below.`}
      >
        <div className="chart-grid">
          <span>{max}</span>
          <span>{Math.round(max / 2)}</span>
          <span>0</span>
        </div>
        <div className="bars">
          {rows.map((row, i) => (
            <div
              className="bar-slot"
              key={i}
              title={`${row.t || row.bucket}: ${keys.map((k, j) => labels[j] + " " + row[k]).join(", ")}`}
            >
              {keys.map((key, j) => (
                <div
                  key={key}
                  className={"bar bar-" + j}
                  style={{ height: `${(Number(row[key] || 0) / max) * 100}%` }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="chart-axis">
        <span>
          {rows[0]?.t
            ? new Date(String(rows[0].t)).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "2-digit",
              })
            : rows[0]?.bucket}
        </span>
        <span>{rows.at(-1)?.t ? "Now" : rows.at(-1)?.bucket}</span>
      </div>
      <details className="chart-table">
        <summary>View chart data</summary>
        <div className="table-scroll">
          <table>
            <caption>{name}</caption>
            <thead>
              <tr>
                <th scope="col">Bucket</th>
                {labels.map((l) => (
                  <th scope="col" key={l}>
                    {l}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <th scope="row">{r.t ? absolute(String(r.t)) : r.bucket}</th>
                  {keys.map((k) => (
                    <td key={k}>{r[k]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
export function Modal({
  title: heading,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const headingId = useId();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const target = document.activeElement as HTMLElement;
    ref.current?.showModal();
    ref.current
      ?.querySelector<HTMLInputElement>("input:not([disabled])")
      ?.focus();
    return () => target?.focus();
  }, []);
  return (
    <dialog
      aria-labelledby={headingId}
      ref={ref}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <header>
        <h2 id={headingId}>{heading}</h2>
        <button
          aria-label="Close dialog"
          className="icon-button"
          onClick={onClose}
        >
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
