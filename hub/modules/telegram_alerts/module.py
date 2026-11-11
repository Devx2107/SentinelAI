"""Telegram alerts module.

Polls the events table for rows newer than the last one seen, applies the
alert policy and hands messages to a background sender. It watches the
database rather than hooking event creation, so it covers events from every
module (and any future writer) without changing them, and a Telegram outage can
never delay or break event logging.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from database.db import db_cursor
from database.models.event import Event
from modules.base_module import BaseModule
from modules.telegram_alerts.policy import AlertPolicy
from modules.telegram_alerts.sender import TelegramSender

logger = logging.getLogger(__name__)

MODULE_ID = "telegram_alerts"
BATCH_SIZE = 100


class TelegramAlertsModule(BaseModule):
    module_id = MODULE_ID

    def __init__(self, settings=None, *, sender=None, policy: Optional[AlertPolicy] = None) -> None:
        if settings is None:
            from config import config

            settings = config.telegram
        self._settings = settings
        self._sender = sender
        self._policy = policy
        self._cursor: Optional[int] = None
        self._started_at: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- BaseModule -----------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        if self._sender is None:
            if not self._settings.enabled:
                logger.info("Telegram alerts are not configured; module idle")
                return
            self._sender = TelegramSender(self._settings.bot_token, self._settings.chat_id)
        if self._policy is None:
            try:
                self._policy = AlertPolicy(
                    self._settings.min_severity,
                    self._settings.cooldown_seconds,
                    self._settings.max_per_minute,
                )
            except ValueError as exc:
                # Misconfigured alerts must never stop the hub from starting.
                logger.error("Telegram alerts disabled: %s", exc)
                return

        # Baseline now so only events written after startup can alert. The start
        # time is kept so a baseline that could not be read yet can be rebuilt
        # later without skipping events written in the meantime.
        self._started_at = datetime.now(timezone.utc).isoformat()
        try:
            self._cursor = self._fetch_latest_id()
        except Exception:
            logger.warning("Could not read the latest event id yet; will retry", exc_info=True)
            self._cursor = None

        self._sender.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="telegram-alerts", daemon=True)
        self._thread.start()
        logger.info(
            "Telegram alerts started (minimum severity: %s)", self._settings.min_severity.lower()
        )

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=max(5.0, self._settings.poll_seconds + 1.0))
        if self._sender is not None:
            self._sender.stop()
        logger.info("Telegram alerts stopped")

    # -- polling --------------------------------------------------------

    def _run(self) -> None:
        failing = False
        while not self._stop.is_set():
            try:
                self.poll_once()
                if failing:
                    logger.info("Telegram alerts: event polling recovered")
                    failing = False
            except Exception:
                if not failing:
                    logger.exception("Telegram alerts: event polling failed; will retry")
                    failing = True
            self._stop.wait(self._settings.poll_seconds)

    def poll_once(self) -> int:
        """Process new events once. Returns how many alerts were queued."""
        latest = self._fetch_latest_id()
        if self._cursor is None:
            # The baseline could not be read at startup. Resume from the last
            # event written before startup so nothing logged since then is lost.
            if self._started_at is None:
                self._cursor = latest
                return 0
            self._cursor = self._fetch_last_id_before(self._started_at)
        elif latest < self._cursor:
            logger.warning("Event ids moved backwards (database replaced?); resetting the cursor")
            self._cursor = latest
            return 0

        queued = 0
        while self._cursor < latest:
            events = self._fetch_after(self._cursor, BATCH_SIZE)
            if not events:
                break
            for event in events:
                text = self._policy.evaluate(event)
                if text is not None and self._sender.submit(text):
                    queued += 1
            self._cursor = events[-1].id
        return queued

    # -- database access ------------------------------------------------

    @staticmethod
    def _fetch_latest_id() -> int:
        with db_cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(id), 0) AS latest FROM events")
            return int(cur.fetchone()["latest"])

    @staticmethod
    def _fetch_last_id_before(moment: str) -> int:
        # julianday() reads both ISO-8601 and "YYYY-MM-DD HH:MM:SS" timestamps.
        with db_cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(id), 0) AS last FROM events WHERE julianday(timestamp) < julianday(?)",
                (moment,),
            )
            return int(cur.fetchone()["last"])

    @staticmethod
    def _fetch_after(after_id: int, limit: int) -> list[Event]:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, timestamp, node_id, sensor, status, severity, confidence, message
                FROM events WHERE id > ? ORDER BY id LIMIT ?
                """,
                (after_id, limit),
            )
            rows = cur.fetchall()
        return [
            Event(
                id=row["id"],
                timestamp=row["timestamp"],
                node_id=row["node_id"],
                sensor=row["sensor"],
                status=row["status"],
                severity=row["severity"],
                confidence=row["confidence"],
                message=row["message"],
            )
            for row in rows
        ]
