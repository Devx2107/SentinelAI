"""Non-blocking Telegram delivery on a dedicated thread.

python-telegram-bot is async-only while the hub is synchronous, so this class
owns one daemon thread running its own asyncio loop. Callers hand messages over
through a bounded queue and never wait on the network. The library is imported
only when the thread starts, so the rest of the hub, the demo and the tests do
not need it installed.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from datetime import timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MAX_RETRY_AFTER_SECONDS = 60.0
_PERMANENT = {"BadRequest", "Forbidden", "ChatMigrated", "Conflict"}


def default_bot_factory(token: str) -> Any:
    from telegram import Bot
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(
        connect_timeout=10.0, read_timeout=15.0, write_timeout=15.0, pool_timeout=5.0
    )
    return Bot(token=token, request=request)


def _seconds(value: Any) -> float:
    if isinstance(value, timedelta):
        value = value.total_seconds()
    try:
        return min(max(float(value), 0.0), MAX_RETRY_AFTER_SECONDS)
    except (TypeError, ValueError):
        return 1.0


def classify_error(exc: BaseException) -> tuple[str, float]:
    """Return (kind, wait) where kind is retry, permanent or fatal.

    Classification goes by class name so this module does not import the
    library. Order matters: python-telegram-bot's BadRequest subclasses
    NetworkError but is not worth retrying.
    """
    names = {cls.__name__ for cls in type(exc).__mro__}
    if "InvalidToken" in names:
        return "fatal", 0.0
    if "RetryAfter" in names:
        return "retry", _seconds(getattr(exc, "retry_after", 1))
    if names & _PERMANENT:
        return "permanent", 0.0
    if "NetworkError" in names or isinstance(exc, (OSError, TimeoutError, asyncio.TimeoutError)):
        return "retry", 0.0
    return "permanent", 0.0


class TelegramSender:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        bot_factory: Optional[Callable[[str], Any]] = None,
        queue_size: int = 50,
        retry_delays: tuple[float, ...] = (1.0, 3.0, 10.0),
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._bot_factory = bot_factory or default_bot_factory
        self._retry_delays = retry_delays
        self._queue: queue.Queue[str] = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._disabled = False
        self._thread: Optional[threading.Thread] = None
        self.dropped = 0

    # -- public API -----------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._thread_main, name="telegram-sender", daemon=True
        )
        self._thread.start()

    def submit(self, text: str) -> bool:
        """Queue a message without blocking. Drops the oldest one when full."""
        if self._disabled:
            return False
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            logger.warning("Telegram queue full; dropped the oldest pending alert")
            try:
                self._queue.put_nowait(text)
            except queue.Full:
                self.dropped += 1
                return False
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                logger.warning("Telegram sender did not stop within %.0fs", timeout)
        pending = self._queue.qsize()
        if pending:
            logger.warning("Telegram sender stopped with %d undelivered alert(s)", pending)

    # -- worker thread --------------------------------------------------

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception:
            self._disabled = True
            logger.exception("Telegram sender stopped unexpectedly")

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "<token>") if self._token else text

    def _describe(self, exc: BaseException) -> str:
        return f"{type(exc).__name__}: {self._redact(str(exc))[:200]}"

    async def _run(self) -> None:
        try:
            bot = self._bot_factory(self._token)
        except Exception as exc:
            self._disabled = True
            logger.error("Telegram alerts unavailable: %s", self._describe(exc))
            return

        try:
            try:
                await bot.initialize()
                logger.info("Telegram alerts ready (bot @%s)", getattr(bot, "username", "?"))
            except Exception as exc:
                kind, _ = classify_error(exc)
                if kind == "fatal":
                    self._disabled = True
                    logger.error("Telegram bot token was rejected; alerts disabled")
                    return
                logger.warning(
                    "Could not verify the Telegram bot yet (%s); will keep trying to send",
                    self._describe(exc),
                )

            while not self._stop.is_set() and not self._disabled:
                text = await asyncio.to_thread(self._next_text)
                if text is not None:
                    await self._deliver(bot, text)
        finally:
            try:
                await bot.shutdown()
            except Exception:
                logger.debug("Telegram bot shutdown failed", exc_info=True)

    def _next_text(self) -> Optional[str]:
        try:
            return self._queue.get(timeout=0.25)
        except queue.Empty:
            return None

    async def _sleep(self, seconds: float) -> None:
        remaining = seconds
        while remaining > 0 and not self._stop.is_set():
            step = min(0.25, remaining)
            await asyncio.sleep(step)
            remaining -= step

    async def _deliver(self, bot: Any, text: str) -> bool:
        attempts = len(self._retry_delays) + 1
        for attempt in range(attempts):
            try:
                await bot.send_message(chat_id=self._chat_id, text=text)
                return True
            except Exception as exc:
                kind, wait = classify_error(exc)
                if kind == "fatal":
                    self._disabled = True
                    logger.error("Telegram bot token was rejected; alerts disabled")
                    return False
                if kind == "permanent":
                    logger.warning("Telegram rejected an alert: %s", self._describe(exc))
                    return False
                if attempt + 1 >= attempts or self._stop.is_set():
                    logger.warning(
                        "Giving up on a Telegram alert after %d attempt(s): %s",
                        attempt + 1,
                        self._describe(exc),
                    )
                    return False
                await self._sleep(max(wait, self._retry_delays[attempt]))
        return False
