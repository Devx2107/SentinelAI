"""Single source of truth for MQTT topic naming.

Both the hub and any future node agents (RPi 0 W, Arduino bridge) must
import from this module rather than constructing topic strings by hand.
This prevents topic-name typos causing silent message loss, which is
one of the most common bugs in MQTT-based systems.

Topic convention:

    sentinelai/<node_id>/status               -> "online" / "offline" (retained, LWT)
    sentinelai/<node_id>/heartbeat             -> periodic liveness ping
    sentinelai/<node_id>/<sensor_id>/state     -> sensor state changes
    sentinelai/hub/commands/<node_id>          -> hub -> node commands (future use)
"""

from __future__ import annotations


def status_topic(node_id: str) -> str:
    """Topic a node publishes its online/offline status to (retained + LWT)."""
    return f"sentinelai/{node_id}/status"


def heartbeat_topic(node_id: str) -> str:
    """Topic a node publishes periodic liveness pings to."""
    return f"sentinelai/{node_id}/heartbeat"


def sensor_state_topic(node_id: str, sensor_id: str) -> str:
    """Topic a node publishes a specific sensor's state changes to."""
    return f"sentinelai/{node_id}/{sensor_id}/state"


def command_topic(node_id: str) -> str:
    """Topic the hub publishes commands to a specific node on."""
    return f"sentinelai/hub/commands/{node_id}"


# Wildcard subscriptions the hub uses to listen to *all* nodes at once.
ALL_STATUS_WILDCARD = "sentinelai/+/status"
ALL_HEARTBEAT_WILDCARD = "sentinelai/+/heartbeat"
ALL_SENSOR_STATE_WILDCARD = "sentinelai/+/+/state"
