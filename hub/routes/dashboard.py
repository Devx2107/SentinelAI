"""Dashboard routes for the SentinelAI hub."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, Response, render_template, request

from config import config
from database.models.device import list_devices
from database.models.event import list_events

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")
_APP_STARTED_AT = datetime.now(timezone.utc)

_REALM = "SentinelAI Dashboard"


def _dashboard_credentials() -> tuple[str | None, str | None]:
    return (
        os.getenv("SENTINELAI_DASHBOARD_USER"),
        os.getenv("SENTINELAI_DASHBOARD_PASSWORD"),
    )


def _unauthorized_response() -> Response:
    response = Response("Unauthorized", 401)
    response.headers["WWW-Authenticate"] = f'Basic realm="{_REALM}"'
    return response


def _require_dashboard_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        expected_user, expected_password = _dashboard_credentials()
        authorization = request.authorization

        if not expected_user or not expected_password:
            return Response("Dashboard credentials are not configured.", 500)

        if (
            authorization is None
            or authorization.username != expected_user
            or authorization.password != expected_password
        ):
            return _unauthorized_response()

        return func(*args, **kwargs)

    return wrapper


def _format_timestamp(timestamp: str | None) -> str:
    if not timestamp:
        return "Unknown"

    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_capabilities(capabilities: list[str] | None) -> str:
    if not capabilities:
        return "None declared"
    return ", ".join(capabilities)


def _format_confidence(confidence: float | None) -> str:
    if confidence is None:
        return "-"
    return f"{confidence:.2f}"


def _format_uptime(elapsed: timedelta) -> str:
    total_seconds = int(elapsed.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _severity_class(severity: str) -> str:
    normalized = (severity or "unknown").strip().lower()
    if normalized in {"critical", "high"}:
        return "severity-critical"
    if normalized in {"warning", "warn"}:
        return "severity-warning"
    if normalized in {"info", "informational"}:
        return "severity-info"
    return "severity-unknown"


def _device_view_models() -> list[dict[str, str]]:
    devices = list_devices()
    return [
        {
            "node_id": device.node_id,
            "status": device.status,
            "status_class": f"status-{device.status.strip().lower().replace(' ', '-')}",
            "last_seen": _format_timestamp(device.last_seen),
            "capabilities": _format_capabilities(device.capabilities),
        }
        for device in devices
    ]


def _event_view_models(sensor_filter: str | None = None) -> list[dict[str, str]]:
    events = list_events(limit=50, sensor=sensor_filter)
    return [
        {
            "timestamp": _format_timestamp(event.timestamp),
            "node_id": event.node_id,
            "sensor": event.sensor,
            "status": event.status,
            "severity": event.severity,
            "severity_class": _severity_class(event.severity),
            "message": event.message,
            "confidence": _format_confidence(event.confidence),
        }
        for event in events
    ]


@dashboard_bp.get("/", strict_slashes=False)
@_require_dashboard_auth
def dashboard_page() -> str:
    sensor_filter = (request.args.get("sensor") or "").strip() or None
    devices = _device_view_models()
    events = _event_view_models(sensor_filter=sensor_filter)
    uptime = _format_uptime(datetime.now(timezone.utc) - _APP_STARTED_AT)
    return render_template(
        "dashboard.html",
        devices=devices,
        events=events,
        node_id=config.node.node_id,
        uptime=uptime,
        sensor_filter=sensor_filter or "",
    )


@dashboard_bp.get("/devices")
@_require_dashboard_auth
def devices_partial() -> str:
    devices = _device_view_models()
    return render_template("_devices_partial.html", devices=devices)


@dashboard_bp.get("/events")
@_require_dashboard_auth
def events_partial() -> str:
    sensor_filter = (request.args.get("sensor") or "").strip() or None
    events = _event_view_models(sensor_filter=sensor_filter)
    return render_template(
        "_events_partial.html",
        events=events,
        sensor_filter=sensor_filter or "",
    )
