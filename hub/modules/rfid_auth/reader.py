"""Card reader abstractions for RFID authentication."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

CardCallback = Callable[[str], None]


class BaseCardReader(ABC):
    """Interface for RC522-like card readers."""

    @abstractmethod
    def on_card(self, callback: CardCallback) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class ManualCardReader(BaseCardReader):
    """Development/test helper that emits card IDs manually."""

    def __init__(self) -> None:
        self._callbacks: list[CardCallback] = []

    def on_card(self, callback: CardCallback) -> None:
        self._callbacks.append(callback)

    def scan(self, card_uid: str) -> None:
        for callback in self._callbacks:
            callback(card_uid)

    def close(self) -> None:
        self._callbacks.clear()

