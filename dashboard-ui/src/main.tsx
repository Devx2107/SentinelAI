import { useEffect, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { api, clearCredentials, setCredentials } from "./api/client";
import type { SystemInfo } from "./api/types";
import { useStream } from "./hooks";
import { Icon } from "./components";
import {
  AccessPage,
  DeviceDetail,
  DevicesPage,
  EntryPage,
  EventsPageView,
  OverviewPage,
  SystemPage,
} from "./pages";
import "./styles.css";
const nav = [
  ["/", "overview", "Overview"],
  ["/events", "events", "Events"],
  ["/devices", "devices", "Devices"],
  ["/access", "access", "Access"],
  ["/entry-monitor", "entry", "Entry monitor"],
  ["/system", "system", "System"],
];
function App() {
  const [session, setSession] = useState<SystemInfo | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const stream = useStream(!!session);
  const location = useLocation();
  useEffect(() => {
    const logout = () => {
      clearCredentials();
      setSession(null);
    };
    window.addEventListener("sentinel-unauthorized", logout);
    return () => window.removeEventListener("sentinel-unauthorized", logout);
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
    document.getElementById("main")?.focus();
  }, [location.pathname]);
  const login = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    setCredentials(String(data.get("username")), String(data.get("password")));
    try {
      setSession(await api<SystemInfo>("/system"));
    } catch (e) {
      clearCredentials();
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (!session)
    return (
      <main className="login">
        <div className="login-art">
          <div className="brand">
            <Icon name="shield" size={31} />
            <span>
              sentinel<span className="brand-ai">ai</span>
            </span>
          </div>
          <div className="login-copy">
            <div className="eyebrow">A QUIETER KIND OF SECURITY</div>
            <h1>
              Your home.
              <br />
              In good sight.
            </h1>
            <p>
              One calm place for every signal.
              <br />
              See your devices, understand activity,
              <br />
              and know who comes home.
            </p>
            <div className="orb">
              <Icon name="shield" size={90} />
            </div>
          </div>
          <span className="login-foot">LOCAL FIRST. ALWAYS AWARE.</span>
        </div>
        <div className="login-form">
          <div className="eyebrow">SENTINELAI CONTROL ROOM</div>
          <h2>Welcome back.</h2>
          <p>Sign in to your hub to see the whole picture.</p>
          <form onSubmit={login}>
            <label>
              Username
              <input
                name="username"
                autoComplete="username"
                required
                autoFocus
                placeholder="Your username"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="Your password"
              />
            </label>
            {error && (
              <p className="inline-error" role="alert">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? "Connecting…" : "Enter control room"}
              <Icon name="arrow" size={18} />
            </button>
          </form>
          <p className="login-help">
            Standalone demo: <code>admin</code> / <code>dev</code>.<br />
            Live hubs use the credentials configured on your device.
          </p>
          <div className="privacy-note">
            <Icon name="access" size={16} /> Credentials stay in this tab’s
            memory.
          </div>
        </div>
      </main>
    );
  return (
    <div className="shell">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link className="brand" to="/">
          <Icon name="shield" size={31} />
          <span>
            sentinel<span className="brand-ai">ai</span>
          </span>
        </Link>
        <div className="workspace">
          <span className="workspace-avatar">S</span>
          <div>
            <strong>Home network</strong>
            <small>{session.node_id} · local hub</small>
          </div>
          <span className="workspace-dot" />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {nav.map(([path, icon, label]) => (
            <NavLink key={path} end={path === "/"} to={path}>
              <Icon name={icon} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <Icon name="shield" />
            <strong>Built for your peace of mind.</strong>
            <p>
              Your data stays on your hub.
              <br />
              Your space stays yours.
            </p>
          </div>
          <div className="version">
            SENTINEL OS <span>v2.0</span>
          </div>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            <strong>
              {nav.find(
                ([p]) => p !== "/" && location.pathname.startsWith(p),
              )?.[2] || "Overview"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className={"stream-state " + stream.status}>
              <i />
              {stream.status === "live"
                ? "Live connection"
                : stream.status === "polling"
                  ? "Polling · reconnecting"
                  : stream.status === "connecting"
                    ? "Connecting…"
                    : "Reconnecting…"}
            </span>
            <span className="mode">{session.mode.toUpperCase()}</span>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={() => {
                clearCredentials();
                setSession(null);
              }}
            >
              <Icon name="logout" size={19} />
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<OverviewPage {...stream} />} />
            <Route path="/events" element={<EventsPageView {...stream} />} />
            <Route path="/devices" element={<DevicesPage {...stream} />} />
            <Route path="/devices/:id" element={<DeviceDetail {...stream} />} />
            <Route path="/access" element={<AccessPage {...stream} />} />
            <Route path="/entry-monitor" element={<EntryPage {...stream} />} />
            <Route path="/system" element={<SystemPage {...stream} />} />
            <Route
              path="*"
              element={
                <div className="state">
                  <h1>Page not found</h1>
                  <Link to="/">Return to overview</Link>
                </div>
              }
            />
          </Routes>
          <footer className="page-footer">
            <span>
              <Icon name="shield" size={14} />
              SentinelAI · Local by design
            </span>
            <span>
              {new Date().toLocaleDateString(undefined, {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </footer>
        </main>
      </div>
      <div className="sr-only" aria-live="assertive">
        {stream.critical}
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <BrowserRouter basename="/app">
    <App />
  </BrowserRouter>,
);
