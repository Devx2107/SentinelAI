"""SentinelAI hub entrypoint.

Startup sequence:
    1. Initialize the database (create tables if missing)
    2. Connect to the MQTT broker
    3. Register the hub itself in the device registry
    4. Start all modules (Phase 1: entry_monitor)
    5. Serve a minimal Flask app (health check only for now —
       dashboard routes/templates come once this pipeline is proven)

Run with: python app.py
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType
from typing import Optional

from flask import Flask, jsonify

from config import config
from core.device_registry import DeviceRegistry
from core.module_loader import ModuleLoader
from core.mqtt_client import get_mqtt_client
from database.db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_module_loader: Optional[ModuleLoader] = None


@app.route("/api/health")
def health() -> "flask.Response":
    """Basic liveness check — full status endpoints come with the dashboard."""
    return jsonify({"status": "ok", "node_id": config.node.node_id})


def _shutdown(signum: int, _frame: Optional[FrameType]) -> None:
    logger.info("Received signal %s, shutting down...", signum)
    if _module_loader is not None:
        _module_loader.stop_all()
    get_mqtt_client().disconnect()
    sys.exit(0)


def main() -> None:
    global _module_loader

    logger.info("Starting SentinelAI hub (node_id=%s)", config.node.node_id)

    init_db()

    mqtt_client = get_mqtt_client()
    mqtt_client.connect()

    device_registry = DeviceRegistry()
    device_registry.register_with_mqtt(mqtt_client)
    device_registry.register_local_device(
        node_id=config.node.node_id,
        capabilities=["pir", "camera", "entry_monitor"],
    )

    _module_loader = ModuleLoader(mqtt_client=mqtt_client)
    _module_loader.start_all()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Hub is running. Press Ctrl+C to stop.")
    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
