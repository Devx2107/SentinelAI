"""Module loader.

Starts every registered BaseModule at hub startup and stops them
cleanly at shutdown. For Phase 1 this is an explicit registry rather
than filesystem auto-discovery - with only one real module built so
far, magic directory-scanning would add complexity without payoff.
As more modules come online (motion_monitor, environment, rfid_auth),
this is the one place that needs a new line added; nothing else in
the hub needs to change.
"""

from __future__ import annotations

import logging

from core.auth_state import RfidAuthState
from modules.base_module import BaseModule

logger = logging.getLogger(__name__)


def build_modules(mqtt_client, auth_state=None, reader=None) -> list[BaseModule]:
    """Construct every module SentinelAI currently ships."""
    modules: list[BaseModule] = []
    from config import config
    auth_state = auth_state or RfidAuthState(config.rfid.auth_window_seconds)

    try:
        from modules.entry_monitor.module import EntryMonitorModule
    except ModuleNotFoundError as exc:
        logger.warning(
            "Skipping entry_monitor module because a hardware dependency is unavailable: %s",
            exc,
        )
    else:
        modules.append(EntryMonitorModule(mqtt_client=mqtt_client, auth_state=auth_state))

    from modules.rfid_auth.module import RfidAuthModule

    modules.append(RfidAuthModule(mqtt_client=mqtt_client, auth_state=auth_state, reader=reader))

    return modules


class ModuleLoader:
    """Starts and stops the full set of hub modules as a unit."""

    def __init__(self, mqtt_client, reader=None) -> None:
        from config import config
        self.auth_state = RfidAuthState(config.rfid.auth_window_seconds)
        self._modules = build_modules(mqtt_client, self.auth_state, reader)
        self._started = []
        # Constructors may allocate hardware before start() is called.
        self._cleanup_pending = list(self._modules)

    def start_all(self) -> None:
        for module in self._modules:
            if module in self._started:
                continue
            logger.info("Starting module '%s'", module.module_id)
            self._started.append(module)
            try:
                module.start()
            except Exception:
                self.stop_all()
                raise

    def stop_all(self) -> None:
        while self._cleanup_pending:
            module = self._cleanup_pending.pop()
            logger.info("Stopping module '%s'", module.module_id)
            try:
                module.stop()
            except Exception:
                logger.exception("Error stopping module '%s'", module.module_id)
