"""Hardware-free, network-free tests for Telegram alerts."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import tempfile
import threading
import time
from datetime import timedelta
from unittest.mock import Mock

import pytest

import config as config_module
import run
from config import TelegramConfig
from database.models.event import Event, create_event
from modules.telegram_alerts import module as module_mod
from modules.telegram_alerts.module import TelegramAlertsModule
from modules.telegram_alerts.policy import AlertPolicy, format_alert, mask_card_uid
from modules.telegram_alerts.sender import TelegramSender, classify_error

TOKEN = "123456789:AAH-fake_token_value_0123456789abcd"


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
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


def make_event(severity="warning", status="person_confirmed", node="hub", sensor="entry_monitor", **kw):
    kw.setdefault("message", "Person detected at the entry")
    return Event(node_id=node, sensor=sensor, status=status, severity=severity, **kw)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeSender:
    def __init__(self):
        self.messages = []
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def submit(self, text):
        self.messages.append(text)
        return True

    def stop(self):
        self.stopped = True


def settings(**overrides):
    values = dict(
        bot_token=TOKEN, chat_id="42", min_severity="warning",
        cooldown_seconds=60.0, poll_seconds=0.01, max_per_minute=20,
    )
    values.update(overrides)
    return TelegramConfig(**values)


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ---------------------------------------------------------------- config


def test_telegram_is_disabled_unless_token_and_chat_id_are_set():
    assert not TelegramConfig(bot_token="", chat_id="").enabled
    assert not TelegramConfig(bot_token=TOKEN, chat_id="").enabled
    assert not TelegramConfig(bot_token="", chat_id="42").enabled
    assert TelegramConfig(bot_token=TOKEN, chat_id="42").enabled


def test_token_is_not_exposed_in_config_repr():
    assert TOKEN not in repr(TelegramConfig(bot_token=TOKEN, chat_id="42"))
    assert TOKEN not in repr(config_module.config)


# ---------------------------------------------------------------- policy


def test_default_threshold_alerts_on_warning_and_critical_only():
    policy = AlertPolicy("warning", cooldown_seconds=0)
    assert policy.evaluate(make_event("info")) is None
    assert policy.evaluate(make_event("warning")) is not None
    assert policy.evaluate(make_event("critical")) is not None


def test_critical_threshold_ignores_warnings_and_info_allows_everything():
    strict = AlertPolicy("critical", cooldown_seconds=0)
    assert strict.evaluate(make_event("warning")) is None
    assert strict.evaluate(make_event("critical")) is not None
    assert AlertPolicy("INFO", cooldown_seconds=0).evaluate(make_event("info")) is not None


def test_unknown_severity_is_treated_as_warning():
    assert AlertPolicy("warning").evaluate(make_event("high")) is not None
    assert AlertPolicy("critical").evaluate(make_event("high")) is None


def test_invalid_minimum_severity_is_rejected():
    with pytest.raises(ValueError):
        AlertPolicy("urgent")


def test_cooldown_suppresses_repeats_and_reports_the_count():
    clock = Clock()
    policy = AlertPolicy("warning", cooldown_seconds=60, clock=clock)
    assert policy.evaluate(make_event()) is not None
    clock.now += 10
    assert policy.evaluate(make_event()) is None
    clock.now += 10
    assert policy.evaluate(make_event()) is None
    clock.now += 60
    text = policy.evaluate(make_event())
    assert text is not None and "+2 similar" in text
    clock.now += 61
    assert "suppressed" not in policy.evaluate(make_event())


def test_cooldown_is_tracked_per_node_sensor_and_status():
    policy = AlertPolicy("warning", cooldown_seconds=60, clock=Clock())
    assert policy.evaluate(make_event()) is not None
    assert policy.evaluate(make_event(status="other")) is not None
    assert policy.evaluate(make_event(sensor="rfid_auth")) is not None
    assert policy.evaluate(make_event(node="node-2")) is not None
    assert policy.evaluate(make_event()) is None


def test_zero_cooldown_sends_every_event():
    policy = AlertPolicy("warning", cooldown_seconds=0, clock=Clock())
    assert all(policy.evaluate(make_event()) for _ in range(5))


def test_global_rate_cap_applies_across_event_types_and_recovers():
    clock = Clock()
    policy = AlertPolicy("warning", cooldown_seconds=0, max_per_minute=2, clock=clock)
    assert policy.evaluate(make_event(status="a")) is not None
    assert policy.evaluate(make_event(status="b")) is not None
    assert policy.evaluate(make_event(status="c")) is None
    clock.now += 61
    text = policy.evaluate(make_event(status="c"))
    assert text is not None and "+1 similar" in text


def test_message_contains_the_useful_fields():
    event = make_event(
        "critical", confidence=0.923, timestamp="2026-11-11T10:30:00+00:00",
        message="Glass break",
    )
    text = format_alert(event)
    assert "CRITICAL" in text and "person_confirmed" in text and "Glass break" in text
    assert "Node: hub" in text and "Sensor: entry_monitor" in text
    assert "Confidence: 92%" in text
    assert "Time: 2026-11-11 10:30:00 UTC" in text


def test_non_utc_and_unparseable_timestamps_are_handled():
    assert "10:30:00 UTC" in format_alert(make_event(timestamp="2026-11-11T16:00:00+05:30"))
    assert "Time: not-a-time" in format_alert(make_event(timestamp="not-a-time"))


def test_long_messages_are_truncated():
    assert len(format_alert(make_event(message="x" * 5000))) < 800


def test_rfid_card_uid_is_masked_to_the_last_four_characters():
    assert mask_card_uid("RFID card 04A1B2C3 rejected") == "RFID card ****B2C3 rejected"
    text = format_alert(make_event(sensor="rfid_auth", message="RFID card 04A1B2C3 (Spare) is disabled"))
    assert "04A1B2C3" not in text and "****B2C3" in text and "(Spare)" in text
    assert mask_card_uid("RFID card AB rejected") == "RFID card **** rejected"


# ----------------------------------------------------------------- module


def make_module(**overrides):
    sender = FakeSender()
    values = settings(**overrides)
    policy = AlertPolicy(values.min_severity, values.cooldown_seconds, values.max_per_minute)
    return TelegramAlertsModule(values, sender=sender, policy=policy), sender


def test_existing_history_is_never_replayed_and_new_events_alert():
    create_event(make_event("critical", message="old"))
    module, sender = make_module()
    module.start()
    try:
        create_event(make_event("info", status="quiet"))
        create_event(make_event("warning", message="new one"))
        assert wait_for(lambda: len(sender.messages) == 1)
    finally:
        module.stop()
    assert "new one" in sender.messages[0]
    assert not any("old" in message for message in sender.messages)


def test_events_are_processed_once_across_batches(monkeypatch):
    monkeypatch.setattr(module_mod, "BATCH_SIZE", 2)
    module, sender = make_module(cooldown_seconds=0.0)
    module.poll_once()  # baseline
    for index in range(5):
        create_event(make_event(message=f"event {index}"))
    assert module.poll_once() == 5
    assert module.poll_once() == 0
    assert [m.splitlines()[1] for m in sender.messages] == [f"event {i}" for i in range(5)]


def test_cursor_resets_when_event_ids_move_backwards():
    module, sender = make_module()
    module.poll_once()
    module._cursor = 9999
    assert module.poll_once() == 0
    create_event(make_event(message="after reset"))
    assert module.poll_once() == 1


def test_polling_survives_errors_and_recovers(monkeypatch):
    module, sender = make_module()
    real = TelegramAlertsModule._fetch_latest_id
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if 2 <= calls["n"] <= 3:
            raise RuntimeError("database is locked")
        return real()

    monkeypatch.setattr(module, "_fetch_latest_id", flaky)
    module.start()
    try:
        assert wait_for(lambda: calls["n"] >= 4)
        create_event(make_event(message="after outage"))
        assert wait_for(lambda: len(sender.messages) == 1)
    finally:
        module.stop()


<<<<<<< HEAD
def test_events_written_while_the_database_was_unreadable_at_startup_still_alert(monkeypatch):
    # History from before startup, in every timestamp format seen in the table.
    create_event(make_event("critical", message="old iso", timestamp="2000-01-01T00:00:00+00:00"))
    create_event(make_event("critical", message="old micro", timestamp="2000-01-01T00:00:00.123456+00:00"))
    create_event(make_event("critical", message="old plain", timestamp="2000-01-01 00:00:00"))

    module, sender = make_module()
    real_latest = TelegramAlertsModule._fetch_latest_id
    outage = {"on": True}

    def flaky_latest():
        if outage["on"]:
            raise RuntimeError("database is locked")
        return real_latest()

    monkeypatch.setattr(module, "_fetch_latest_id", flaky_latest)
    module.start()
    try:
        # Logged while the module could not read the database.
        create_event(make_event("warning", message="during outage"))
        outage["on"] = False
        assert wait_for(lambda: len(sender.messages) == 1)
    finally:
        module.stop()
    assert "during outage" in sender.messages[0]
    assert not any("old" in message for message in sender.messages)


=======
>>>>>>> fe2d4f2254e823ea079bf77250df6abd44ffb03e
def test_start_and_stop_are_idempotent_and_clean_up_threads():
    module, sender = make_module()
    module.start()
    module.start()
    assert sender.started
    thread = module._thread
    assert thread.is_alive()
    module.stop()
    module.stop()
    assert sender.stopped and not thread.is_alive() and module._thread is None


def test_unconfigured_module_stays_idle():
    module = TelegramAlertsModule(TelegramConfig(bot_token="", chat_id=""))
    module.start()
    assert module._thread is None
    module.stop()


def test_bad_severity_disables_alerts_without_breaking_startup(caplog):
    sender = FakeSender()
    module = TelegramAlertsModule(settings(min_severity="loud"), sender=sender)
    with caplog.at_level(logging.ERROR):
        module.start()
    assert module._thread is None and not sender.started
    assert "Telegram alerts disabled" in caplog.text


def test_module_is_registered_only_when_telegram_is_configured(monkeypatch):
    from core import module_loader

    ids = [m.module_id for m in module_loader.build_modules(Mock())]
    assert "telegram_alerts" not in ids

    enabled = dataclasses.replace(config_module.config, telegram=settings())
    monkeypatch.setattr(config_module, "config", enabled)
    modules = module_loader.build_modules(Mock())
    assert modules[-1].module_id == "telegram_alerts"


# ----------------------------------------------------------------- sender


class NetworkError(Exception):
    """Mirrors telegram.error.NetworkError by name."""


class TimedOut(NetworkError):
    pass


class BadRequest(NetworkError):
    """PTB's BadRequest subclasses NetworkError; it must still not be retried."""


class Forbidden(Exception):
    pass


class InvalidToken(Exception):
    pass


class RetryAfter(Exception):
    def __init__(self, retry_after):
        super().__init__(f"Flood control. Retry in {retry_after}")
        self.retry_after = retry_after


class FakeBot:
    def __init__(self, outcomes=()):
        self.outcomes = list(outcomes)
        self.sent = []
        self.attempts = 0
        self.initialized = False
        self.shut_down = False
        self.username = "sentinel_test_bot"
        self.init_error = None

    async def initialize(self):
        if self.init_error:
            raise self.init_error
        self.initialized = True

    async def shutdown(self):
        self.shut_down = True

    async def send_message(self, chat_id, text):
        self.attempts += 1
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        self.sent.append((chat_id, text))


def make_sender(bot, **kw):
    kw.setdefault("retry_delays", (0.0, 0.0))
    return TelegramSender(TOKEN, "42", bot_factory=lambda token: bot, **kw)


def test_messages_are_delivered_in_order_to_the_chat():
    bot = FakeBot()
    sender = make_sender(bot)
    sender.start()
    try:
        for text in ("one", "two", "three"):
            assert sender.submit(text)
        assert wait_for(lambda: len(bot.sent) == 3)
    finally:
        sender.stop()
    assert bot.sent == [("42", "one"), ("42", "two"), ("42", "three")]
    assert bot.initialized and bot.shut_down


def test_transient_network_errors_are_retried():
    bot = FakeBot([TimedOut("timed out"), NetworkError("reset")])
    sender = make_sender(bot)
    sender.start()
    try:
        sender.submit("hello")
        assert wait_for(lambda: bot.sent == [("42", "hello")])
    finally:
        sender.stop()
    assert bot.attempts == 3


def test_gives_up_after_the_retry_budget():
    bot = FakeBot([TimedOut("x")] * 10)
    sender = make_sender(bot)
    sender.start()
    try:
        sender.submit("lost")
        sender.submit("next")
        assert wait_for(lambda: bot.sent == [])
        assert wait_for(lambda: bot.attempts >= 4)
    finally:
        sender.stop()
    assert bot.attempts >= 3 and ("42", "lost") not in bot.sent


@pytest.mark.parametrize("retry_after", [0.01, 1, timedelta(milliseconds=10)])
def test_retry_after_is_honoured_for_numeric_and_timedelta_values(retry_after):
    bot = FakeBot([RetryAfter(retry_after if not isinstance(retry_after, int) else 0)])
    sender = make_sender(bot)
    sender.start()
    try:
        sender.submit("flood")
        assert wait_for(lambda: bot.sent == [("42", "flood")])
    finally:
        sender.stop()


def test_bad_request_is_dropped_without_retrying_even_though_it_is_a_network_error():
    bot = FakeBot([BadRequest("chat not found")])
    sender = make_sender(bot)
    sender.start()
    try:
        sender.submit("dropped")
        sender.submit("kept")
        assert wait_for(lambda: bot.sent == [("42", "kept")])
    finally:
        sender.stop()
    assert bot.attempts == 2


def test_invalid_token_disables_the_sender_and_never_logs_the_token(caplog):
    bot = FakeBot([InvalidToken(f"The token `{TOKEN}` was rejected by the server.")])
    sender = make_sender(bot)
    with caplog.at_level(logging.DEBUG):
        sender.start()
        sender.submit("first")
        assert wait_for(lambda: not sender.submit("later"))
        sender.stop()
    assert TOKEN not in caplog.text
    assert bot.sent == []


def test_token_is_redacted_from_logged_errors(caplog):
    bot = FakeBot([Forbidden(f"blocked via https://api.telegram.org/bot{TOKEN}/sendMessage")])
    sender = make_sender(bot)
    with caplog.at_level(logging.DEBUG):
        sender.start()
        sender.submit("x")
        assert wait_for(lambda: bot.attempts == 1)
        sender.stop()
    assert TOKEN not in caplog.text and "<token>" in caplog.text


def test_startup_verification_failure_does_not_stop_delivery(caplog):
    bot = FakeBot()
    bot.init_error = NetworkError("offline at boot")
    sender = make_sender(bot)
    with caplog.at_level(logging.WARNING):
        sender.start()
        sender.submit("still sent")
        assert wait_for(lambda: bot.sent == [("42", "still sent")])
        sender.stop()
    assert "Could not verify" in caplog.text


def test_rejected_token_at_startup_disables_alerts():
    bot = FakeBot()
    bot.init_error = InvalidToken("rejected")
    sender = make_sender(bot)
    sender.start()
    try:
        assert wait_for(lambda: not sender.submit("nope"))
    finally:
        sender.stop()


def test_full_queue_drops_the_oldest_alert():
    bot = FakeBot()
    sender = make_sender(bot, queue_size=2)
    for text in ("a", "b", "c"):
        assert sender.submit(text)
    assert sender.dropped == 1
    sender.start()
    try:
        assert wait_for(lambda: len(bot.sent) == 2)
    finally:
        sender.stop()
    assert [text for _, text in bot.sent] == ["b", "c"]


def test_missing_library_disables_alerts_without_raising(caplog):
    def broken_factory(token):
        raise ImportError("No module named 'telegram'")

    sender = TelegramSender(TOKEN, "42", bot_factory=broken_factory)
    with caplog.at_level(logging.ERROR):
        sender.start()
        assert wait_for(lambda: not sender.submit("x"))
        sender.stop()
    assert "unavailable" in caplog.text


def test_stop_returns_promptly_and_ends_the_thread():
    sender = make_sender(FakeBot())
    sender.start()
    thread = sender._thread
    started = time.monotonic()
    sender.stop()
    assert time.monotonic() - started < 3
    assert not thread.is_alive()


def test_submit_never_blocks_the_caller_while_the_network_is_slow():
    release = threading.Event()

    class SlowBot(FakeBot):
        async def send_message(self, chat_id, text):
            await asyncio.to_thread(release.wait, 5)
            self.sent.append((chat_id, text))

    bot = SlowBot()
    sender = make_sender(bot)
    sender.start()
    try:
        started = time.monotonic()
        for index in range(10):
            sender.submit(f"m{index}")
        assert time.monotonic() - started < 0.5
    finally:
        release.set()
        sender.stop()


def test_error_classification():
    assert classify_error(InvalidToken("x"))[0] == "fatal"
    assert classify_error(RetryAfter(3)) == ("retry", 3.0)
    assert classify_error(RetryAfter(timedelta(seconds=5))) == ("retry", 5.0)
    assert classify_error(RetryAfter(9999))[1] == 60.0
    assert classify_error(BadRequest("x"))[0] == "permanent"
    assert classify_error(Forbidden("x"))[0] == "permanent"
    assert classify_error(TimedOut("x"))[0] == "retry"
    assert classify_error(ConnectionError("x"))[0] == "retry"
    assert classify_error(ValueError("x"))[0] == "permanent"


def test_end_to_end_event_to_message():
    bot = FakeBot()
    module = TelegramAlertsModule(
        settings(), sender=make_sender(bot),
    )
    module.start()
    try:
        create_event(
            make_event(
                sensor="rfid_auth", status="card_denied",
                message="RFID card 04A1B2C3 rejected",
            )
        )
        assert wait_for(lambda: len(bot.sent) == 1)
    finally:
        module.stop()
    chat_id, text = bot.sent[0]
    assert chat_id == "42" and "04A1B2C3" not in text and "****B2C3" in text


def test_real_library_sends_through_the_bot_api_with_a_stubbed_network(monkeypatch):
    pytest.importorskip("telegram")
    import json

    from telegram.request import HTTPXRequest

    calls = []

    async def fake_do_request(self, url, method, request_data=None, *args, **kwargs):
        calls.append((url.rsplit("/", 1)[-1], request_data))
        if url.endswith("/getMe"):
            result = {"id": 1, "is_bot": True, "first_name": "Sentinel", "username": "sentinel_test_bot"}
        else:
            result = {"message_id": 7, "date": 0, "chat": {"id": 42, "type": "private"}, "text": "x"}
        return 200, json.dumps({"ok": True, "result": result}).encode()

    monkeypatch.setattr(HTTPXRequest, "do_request", fake_do_request)
    sender = TelegramSender(TOKEN, "42")
    sender.start()
    try:
        sender.submit("hello from the hub")
        assert wait_for(lambda: any(name == "sendMessage" for name, _ in calls))
    finally:
        sender.stop()
    sent = next(data for name, data in calls if name == "sendMessage")
    assert sent.parameters["chat_id"] == 42 or sent.parameters["chat_id"] == "42"
    assert sent.parameters["text"] == "hello from the hub"


# --------------------------------------------------------------- preflight


@pytest.fixture
def live_env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("SENTINELAI_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("SENTINELAI_DB_PATH", str(tmp_path / "live.db"))
    monkeypatch.setenv("SENTINELAI_DASHBOARD_USER", "admin")
    monkeypatch.setenv("SENTINELAI_DASHBOARD_PASSWORD", "test-secret")
    for name in ("MODEL_PATH", "LABELS_PATH"):
        path = tmp_path / name
        path.write_text("fixture", encoding="utf-8")
        monkeypatch.setenv("SENTINELAI_" + name, str(path))
    monkeypatch.setattr(run.importlib.util, "find_spec", lambda _: object())
    return monkeypatch


def checks():
    return {check["name"]: check for check in run.preflight()}


def test_preflight_passes_with_telegram_unset(live_env):
    assert all(check["ok"] for check in run.preflight())


def test_preflight_passes_with_valid_telegram_settings(live_env):
    live_env.setenv("SENTINELAI_TELEGRAM_BOT_TOKEN", TOKEN)
    live_env.setenv("SENTINELAI_TELEGRAM_CHAT_ID", "-1001234567890")
    live_env.setenv("SENTINELAI_TELEGRAM_MIN_SEVERITY", "Critical")
    assert all(check["ok"] for check in run.preflight())
    assert "python_telegram_bot" in checks()


def test_preflight_accepts_a_channel_name_as_chat_id(live_env):
    live_env.setenv("SENTINELAI_TELEGRAM_BOT_TOKEN", TOKEN)
    live_env.setenv("SENTINELAI_TELEGRAM_CHAT_ID", "@sentinel_alerts")
    assert all(check["ok"] for check in run.preflight())


@pytest.mark.parametrize("env", [
    {"SENTINELAI_TELEGRAM_BOT_TOKEN": TOKEN},
    {"SENTINELAI_TELEGRAM_CHAT_ID": "42"},
])
def test_preflight_requires_both_credentials_or_neither(live_env, env):
    for key, value in env.items():
        live_env.setenv(key, value)
    assert not checks()["telegram_credentials"]["ok"]


@pytest.mark.parametrize("name,value,check", [
    ("BOT_TOKEN", '"123456789:AAH-fake_token_value_0123456789abcd"', "telegram_bot_token"),
    ("BOT_TOKEN", "not-a-token", "telegram_bot_token"),
    ("CHAT_ID", "my chat", "telegram_chat_id"),
    ("MIN_SEVERITY", "loud", "telegram_min_severity"),
    ("COOLDOWN_SECONDS", "-1", "telegram_cooldown_seconds"),
    ("COOLDOWN_SECONDS", "nan", "telegram_cooldown_seconds"),
    ("POLL_SECONDS", "0", "telegram_poll_seconds"),
    ("MAX_PER_MINUTE", "0", "telegram_max_per_minute"),
    ("MAX_PER_MINUTE", "1.5", "telegram_max_per_minute"),
])
def test_preflight_rejects_invalid_telegram_settings(live_env, name, value, check):
    live_env.setenv("SENTINELAI_TELEGRAM_" + name, value)
    assert not checks()[check]["ok"]


def test_preflight_requires_the_library_only_when_alerts_are_enabled(live_env):
    live_env.setattr(run.importlib.util, "find_spec", lambda name: None if name == "telegram" else object())
    assert "python_telegram_bot" not in checks()
    live_env.setenv("SENTINELAI_TELEGRAM_BOT_TOKEN", TOKEN)
    live_env.setenv("SENTINELAI_TELEGRAM_CHAT_ID", "42")
    assert not checks()["python_telegram_bot"]["ok"]


def test_preflight_report_never_contains_the_token(live_env):
    live_env.setenv("SENTINELAI_TELEGRAM_BOT_TOKEN", TOKEN)
    live_env.setenv("SENTINELAI_TELEGRAM_CHAT_ID", "42")
    assert TOKEN not in repr(run.preflight())
