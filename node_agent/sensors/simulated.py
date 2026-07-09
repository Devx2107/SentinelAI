"""Simple in-memory sensors for development and tests."""

from __future__ import annotations

from shared.base_sensor import StateChangeCallback

from node_agent.sensors.polling_sensor import PollingSensor


class SimulatedBinarySensor(PollingSensor):
    """A manually toggled sensor useful for local development and tests."""

    sensor_type = "simulated"
    poll_interval_seconds = 0.1

    def __init__(self, sensor_id: str, initial_state: str = "clear") -> None:
        super().__init__(sensor_id=sensor_id)
        self._state = initial_state

    def read(self) -> str:
        return self._state

    def set_state(self, new_state: str) -> None:
        previous_state = self._state
        self._state = new_state
        if previous_state != new_state:
            self._notify(new_state)

