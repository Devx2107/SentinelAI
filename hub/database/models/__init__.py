"""Database models used by SentinelAI."""

from database.models.device import Device, get_device, list_devices, upsert_device
from database.models.event import Event, create_event, get_latest_event, list_events
from database.models.rfid import KnownCard, get_known_card, list_known_cards, touch_known_card, upsert_known_card

__all__ = [
    "Device",
    "Event",
    "KnownCard",
    "create_event",
    "get_device",
    "get_known_card",
    "get_latest_event",
    "list_devices",
    "list_events",
    "list_known_cards",
    "touch_known_card",
    "upsert_device",
    "upsert_known_card",
]
