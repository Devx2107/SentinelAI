"""Shared RFID authorization state for the hub process."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass(frozen=True)
class AuthSession:
    card_uid: str
    card_label: str
    authorized_at: str
    expires_at: str

    def is_active(self) -> bool:
        return datetime.now(timezone.utc) < datetime.fromisoformat(
            self.expires_at.replace("Z", "+00:00")
        )


class RfidAuthState:
    """Thread-safe in-memory RFID authorization window."""

    def __init__(self, default_window_seconds: float = 30.0) -> None:
        self._default_window_seconds = default_window_seconds
        self._lock = threading.Lock()
        self._session: Optional[AuthSession] = None

    def authorize(
        self,
        card_uid: str,
        card_label: str,
        window_seconds: Optional[float] = None,
    ) -> AuthSession:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=window_seconds or self._default_window_seconds)
        session = AuthSession(
            card_uid=card_uid,
            card_label=card_label,
            authorized_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        with self._lock:
            self._session = session
        return session

    def clear(self) -> None:
        with self._lock:
            self._session = None

    def current(self) -> Optional[AuthSession]:
        with self._lock:
            session = self._session

        if session is None:
            return None

        if not session.is_active():
            self.clear()
            return None

        return session

    def is_authorized(self) -> bool:
        return self.current() is not None

