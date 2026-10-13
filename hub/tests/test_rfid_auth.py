"""Tests for RFID authentication and the known-card registry."""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as config_module  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Point the database at a temp file for the duration of each test."""
    tmp_path = tempfile.mktemp(suffix=".db")
    patched_database = dataclasses.replace(config_module.config.database, path=tmp_path)
    patched_config = dataclasses.replace(config_module.config, database=patched_database)
    monkeypatch.setattr(config_module, "config", patched_config)
    monkeypatch.setattr("database.db.config", patched_config)

    from database.db import init_db

    init_db()
    yield
    if os.path.exists(tmp_path):
        os.remove(tmp_path)


class FakeMQTTClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bool]] = []

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.published.append((topic, payload, retain))


class FakeReader:
    def __init__(self) -> None:
        self._callbacks = []
        self.closed = False

    def on_card(self, callback) -> None:
        self._callbacks.append(callback)

    def scan(self, card_uid: str) -> None:
        for callback in self._callbacks:
            callback(card_uid)

    def close(self) -> None:
        self.closed = True


def test_known_card_registry_round_trip():
    from database.models.rfid import KnownCard, get_known_card, list_known_cards, upsert_known_card

    upsert_known_card(KnownCard(card_uid="04A1B2C3", label="Front Door Keyfob", notes="Primary key"))

    card = get_known_card("04A1B2C3")
    assert card is not None
    assert card.label == "Front Door Keyfob"
    assert list_known_cards()[0].card_uid == "04A1B2C3"


def test_rfid_auth_accepts_known_card_and_publishes_state():
    from core.auth_state import RfidAuthState
    from database.models.rfid import KnownCard, upsert_known_card
    from modules.rfid_auth.module import RfidAuthModule

    upsert_known_card(KnownCard(card_uid="04A1B2C3", label="Front Door Keyfob"))

    mqtt = FakeMQTTClient()
    auth_state = RfidAuthState(default_window_seconds=10)
    module = RfidAuthModule(mqtt_client=mqtt, auth_state=auth_state)

    module.handle_card_uid("04A1B2C3")

    assert auth_state.is_authorized() is True
    assert len(mqtt.published) == 1
    topic, payload, retain = mqtt.published[0]
    assert topic == "sentinelai/hub/rc522_entry/state"
    assert retain is True
    assert "authorized" in payload


def test_rfid_auth_rejects_unknown_card():
    from database.models.event import list_events
    from modules.rfid_auth.module import RfidAuthModule

    mqtt = FakeMQTTClient()
    module = RfidAuthModule(mqtt_client=mqtt)

    module.handle_card_uid("DEADBEEF")

    events = list_events(sensor="rfid_auth")
    assert len(events) == 1
    assert events[0].status == "card_denied"
    assert len(mqtt.published) == 1
    topic, payload, retain = mqtt.published[0]
    assert topic == "sentinelai/hub/rc522_entry/state"
    assert retain is True
    assert "denied" in payload
