"""Tests for the dashboard routes."""

from __future__ import annotations

import base64
import dataclasses
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as config_module  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """Point the database at a temp file for each test run."""
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


@pytest.fixture(autouse=True)
def dashboard_credentials(monkeypatch):
    monkeypatch.setenv("SENTINELAI_DASHBOARD_USER", "admin")
    monkeypatch.setenv("SENTINELAI_DASHBOARD_PASSWORD", "secret")


@pytest.fixture()
def client():
    from app import app as flask_app

    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def _auth_header(username: str = "admin", password: str = "secret") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_dashboard_requires_auth(client):
    response = client.get("/dashboard")

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_dashboard_rejects_invalid_auth(client):
    response = client.get("/dashboard", headers=_auth_header(password="wrong"))

    assert response.status_code == 401


def test_dashboard_renders_shell(client):
    response = client.get("/dashboard", headers=_auth_header())

    assert response.status_code == 200
    assert b"SentinelAI Dashboard" in response.data
    assert b"htmx.org" in response.data


def test_devices_partial_reflects_seeded_devices(client):
    from database.models.device import Device, upsert_device

    upsert_device(Device(node_id="hub", status="online", last_seen="2026-07-09T10:00:00+00:00", capabilities=["pir"]))
    upsert_device(Device(node_id="node-1", status="offline", last_seen="2026-07-09T09:30:00+00:00", capabilities=["dht11"]))

    response = client.get("/dashboard/devices", headers=_auth_header())

    assert response.status_code == 200
    assert b"hub" in response.data
    assert b"node-1" in response.data
    assert b"pir" in response.data
    assert b"dht11" in response.data


def test_events_partial_filters_by_sensor(client):
    from database.models.event import Event, create_event

    create_event(
        Event(
            node_id="hub",
            sensor="entry_monitor",
            status="person_confirmed",
            severity="warning",
            message="Person detected at entry",
            confidence=0.91,
        )
    )
    create_event(
        Event(
            node_id="hub",
            sensor="environment",
            status="temp_ok",
            severity="info",
            message="Temperature within range",
            confidence=0.99,
        )
    )

    response = client.get("/dashboard/events?sensor=entry_monitor", headers=_auth_header())

    assert response.status_code == 200
    assert b"entry_monitor" in response.data
    assert b"environment" not in response.data
    assert b"Person detected at entry" in response.data


def test_dashboard_empty_states_render(client):
    response = client.get("/dashboard", headers=_auth_header())

    assert response.status_code == 200
    assert b"No devices have registered yet." in response.data
    assert b"No events recorded yet." in response.data
