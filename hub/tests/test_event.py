"""Tests for the Event model. Uses a temporary SQLite file so these
tests never touch the real sentinelai.db, and can run on any machine
(no GPIO/camera hardware required).
"""

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as config_module  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Point the database at a temp file for the duration of each test.

    Config dataclasses are frozen (deliberately, to prevent accidental
    mutation at runtime), so we swap in a new Config with an updated
    `database` section rather than mutating the existing one in place.
    """
    patched_database = dataclasses.replace(config_module.config.database, path=str(tmp_path / "events.db"))
    patched_config = dataclasses.replace(config_module.config, database=patched_database)
    monkeypatch.setattr(config_module, "config", patched_config)
    monkeypatch.setattr("database.db.config", patched_config)

    from database.db import init_db

    init_db()
    yield


def test_database_path_can_be_a_plain_filename(monkeypatch, tmp_path):
    from database import db

    monkeypatch.chdir(tmp_path)
    patched = dataclasses.replace(db.config, database=dataclasses.replace(db.config.database, path="local.db"))
    monkeypatch.setattr(db, "config", patched)
    db.init_db()
    assert (tmp_path / "local.db").exists()


def test_create_and_retrieve_event():
    from database.models.event import Event, create_event, get_latest_event

    event = Event(
        node_id="hub",
        sensor="entry_monitor",
        status="person_confirmed",
        severity="warning",
        message="Person confirmed at entry",
        confidence=0.87,
    )
    saved = create_event(event)
    assert saved.id is not None

    latest = get_latest_event(sensor="entry_monitor")
    assert latest is not None
    assert latest.status == "person_confirmed"
    assert latest.confidence == pytest.approx(0.87)


def test_list_events_filters_by_sensor():
    from database.models.event import Event, create_event, list_events

    create_event(
        Event(node_id="hub", sensor="entry_monitor", status="motion_no_person", severity="info", message="no person")
    )
    create_event(
        Event(node_id="hub", sensor="other_sensor", status="ok", severity="info", message="unrelated")
    )

    results = list_events(sensor="entry_monitor")
    assert len(results) == 1
    assert results[0].sensor == "entry_monitor"
