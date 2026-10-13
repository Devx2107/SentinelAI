"""Dependency-injected demo/live seams; no imports of MQTT or hub modules."""
from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Callable, Protocol

from services.common import Store, parse_time, utcnow


class AuthWindowProvider(Protocol):
    def current(self) -> dict | None: ...


class ConnectionStatusProvider(Protocol):
    def current(self) -> dict: ...


class EventSource(Protocol):
    def latest_id(self) -> int: ...
    def after(self, last_id: int, limit: int = 200) -> list[dict]: ...


class DemoAuthWindow:
    def __init__(self, clock=utcnow):
        self.clock, self._value, self._lock = clock, None, Lock()

    def set(self, value):
        with self._lock:
            self._value = dict(value) if value else None

    def current(self):
        with self._lock:
            if self._value and parse_time(self._value['expires_at']) > self.clock():
                return {**self._value, 'active': True}
            return None


class LiveAuthWindow:
    def __init__(self, auth_state):
        self.auth_state = auth_state

    def current(self):
        session = self.auth_state.current()
        if session is None:
            return None
        value = asdict(session)
        return {key: value[key] for key in ('card_uid', 'card_label', 'expires_at')} | {'active': True}


class DemoConnectionStatus:
    def __init__(self, started_at):
        self.started_at = started_at

    def current(self):
        return {'mqtt_connected': None, 'started_at': self.started_at}


class LiveConnectionStatus(DemoConnectionStatus):
    def __init__(self, started_at, is_connected: Callable[[], bool]):
        super().__init__(started_at)
        self.is_connected = is_connected

    def current(self):
        return {'mqtt_connected': bool(self.is_connected()), 'started_at': self.started_at}


class DatabaseEventSource:
    """Shared by demo and live. Synthetic writes are a separate Phase 2 service."""
    def __init__(self, store):
        self.store = store

    def latest_id(self):
        return self.store.rows('SELECT COALESCE(MAX(id), 0) AS id FROM events')[0]['id']

    def after(self, last_id, limit=200):
        return self.store.rows('SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?', (last_id, limit))


@dataclass
class Providers:
    store: Store
    auth: AuthWindowProvider
    connection: ConnectionStatusProvider
    events: EventSource
    node_id: str = 'hub'
    mode: str = 'demo'
    stale_after_seconds: int = 90
    clock: Callable = field(default=utcnow)

    def uptime(self):
        return max(0.0, (self.clock() - self.connection.current()['started_at']).total_seconds())
