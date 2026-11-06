"""Hardware-free tests for EntryMonitorModule and FrameCapture edge cases.

EntryMonitorModule accepts injected pir/camera/detector objects, so every
test here runs against in-memory fakes: no GPIO, camera, model or broker is
touched, on a laptop or on the Pi. Where the module's *default* hardware
constructors are exercised (degraded mode), they are replaced via sys.modules
so a real gpiozero/picamera2/TFLite install can never be reached.

Complements, and does not repeat, test_camera_cleanup.py (FrameCapture
cleanup on failure) and test_lifecycle.py (ModuleLoader rollback).
"""

import dataclasses
import importlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import config as config_module
from core.auth_state import RfidAuthState
from database.models.event import list_events
from modules.entry_monitor import module as em
from shared.mqtt_topics import sensor_state_topic


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Temp database, no real sleeping, and a small deterministic capture window."""
    patched_database = dataclasses.replace(
        config_module.config.database, path=str(tmp_path / "entry.db")
    )
    patched_config = dataclasses.replace(config_module.config, database=patched_database)
    monkeypatch.setattr("database.db.config", patched_config)

    vision = dataclasses.replace(
        em.config.vision, frames_per_capture_window=3, capture_window_seconds=0.0
    )
    monkeypatch.setattr(em, "config", dataclasses.replace(em.config, vision=vision))
    monkeypatch.setattr(em, "time", SimpleNamespace(sleep=lambda _seconds: None))

    from database.db import init_db

    init_db()


class FakePIR:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
        self.callback = None
        self.close_error = None

    def on_change(self, callback):
        self.calls.append("pir.on_change")
        self.callback = callback

    def trigger(self, state):
        self.callback(state)

    def close(self):
        self.calls.append("pir.close")
        if self.close_error:
            raise self.close_error


class FakeCamera:
    def __init__(self, calls=None):
        self.calls = calls if calls is not None else []
        self.frames_captured = 0

    def start(self):
        self.calls.append("camera.start")

    def capture_frame(self):
        self.frames_captured += 1
        return object()

    def stop(self):
        self.calls.append("camera.stop")


class ScriptedDetector:
    """Returns (person_detected, confidence) pairs in order; repeats the last one."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    def detect_person(self, _frame):
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        person, confidence = self._results[index]
        return SimpleNamespace(person_detected=person, confidence=confidence)


def make_module(detector, auth_state=None, calls=None):
    mqtt = Mock()
    pir, camera = FakePIR(calls), FakeCamera(calls)
    module = em.EntryMonitorModule(
        mqtt, auth_state=auth_state, pir=pir, camera=camera, detector=detector
    )
    return module, pir, camera, mqtt


def only_event():
    events = list_events(limit=10)
    assert len(events) == 1
    return events[0]


# --- start / stop ordering ---------------------------------------------------


def test_camera_starts_before_pir_callback_is_registered():
    calls = []
    module, *_ = make_module(ScriptedDetector((False, 0.0)), calls=calls)
    module.start()
    assert calls == ["camera.start", "pir.on_change"]


def test_stop_closes_pir_then_camera_and_is_idempotent():
    calls = []
    module, *_ = make_module(ScriptedDetector((False, 0.0)), calls=calls)
    module.start()
    calls.clear()
    module.stop()
    module.stop()
    assert calls == ["pir.close", "camera.stop"]


def test_camera_is_released_even_if_pir_close_fails():
    calls = []
    module, pir, _camera, _mqtt = make_module(ScriptedDetector((False, 0.0)), calls=calls)
    pir.close_error = RuntimeError("gpio close failed")
    module.start()
    calls.clear()
    with pytest.raises(RuntimeError, match="gpio close failed"):
        module.stop()
    assert calls == ["pir.close", "camera.stop"]


# --- event classification ----------------------------------------------------


def test_person_without_auth_is_a_warning_and_is_published():
    module, pir, _camera, mqtt = make_module(ScriptedDetector((True, 0.87)))
    module.start()
    pir.trigger("motion")

    event = only_event()
    assert (event.sensor, event.status, event.severity) == (
        "entry_monitor",
        "person_confirmed",
        "warning",
    )
    assert event.confidence == pytest.approx(0.87)
    assert "87%" in event.message

    topic, payload = mqtt.publish.call_args.args
    assert topic == sensor_state_topic(em.config.node.node_id, em.SENSOR_ID)
    body = json.loads(payload)
    assert body["state"] == "person_confirmed"
    assert body["confidence"] == pytest.approx(0.87)


def test_motion_without_person_or_auth_is_info():
    module, pir, *_ = make_module(ScriptedDetector((False, 0.3)))
    module.start()
    pir.trigger("motion")

    event = only_event()
    assert (event.status, event.severity) == ("motion_no_person", "info")


def test_person_during_active_rfid_window_is_downgraded_to_info():
    auth = RfidAuthState()
    auth.authorize("04AABBCC", "Dev", window_seconds=60)
    module, pir, *_ = make_module(ScriptedDetector((True, 0.9)), auth_state=auth)
    module.start()
    pir.trigger("motion")

    event = only_event()
    assert (event.status, event.severity) == ("person_confirmed_authenticated", "info")
    assert "RFID auth is active" in event.message


def test_motion_during_active_rfid_window_is_marked_suppressed():
    auth = RfidAuthState()
    auth.authorize("04AABBCC", "Dev", window_seconds=60)
    module, pir, *_ = make_module(ScriptedDetector((False, 0.2)), auth_state=auth)
    module.start()
    pir.trigger("motion")

    event = only_event()
    assert (event.status, event.severity) == ("motion_authenticated", "info")
    assert "alert suppressed" in event.message


def test_expired_rfid_window_does_not_suppress_alerts():
    auth = RfidAuthState()
    auth.authorize("04AABBCC", "Dev", window_seconds=-1)  # already expired
    module, pir, *_ = make_module(ScriptedDetector((True, 0.9)), auth_state=auth)
    module.start()
    pir.trigger("motion")

    event = only_event()
    assert (event.status, event.severity) == ("person_confirmed", "warning")


def test_pir_clear_transition_is_ignored():
    module, pir, camera, mqtt = make_module(ScriptedDetector((True, 0.9)))
    module.start()
    pir.trigger("clear")

    assert list_events(limit=10) == []
    assert camera.frames_captured == 0
    mqtt.publish.assert_not_called()


# --- frame sampling ----------------------------------------------------------


def test_sampling_stops_at_first_person_found():
    # Window is 3 frames; the person appears on frame 2, so frame 3 (0.99)
    # must never be captured or scored.
    detector = ScriptedDetector((False, 0.2), (True, 0.9), (True, 0.99))
    module, pir, camera, _mqtt = make_module(detector)
    module.start()
    pir.trigger("motion")

    assert camera.frames_captured == 2
    assert detector.calls == 2
    event = only_event()
    assert event.status == "person_confirmed"
    assert event.confidence == pytest.approx(0.9)


def test_all_frames_are_sampled_when_nobody_is_found():
    module, pir, camera, _mqtt = make_module(ScriptedDetector((False, 0.2), (False, 0.45), (False, 0.1)))
    module.start()
    pir.trigger("motion")

    assert camera.frames_captured == 3
    event = only_event()
    assert event.status == "motion_no_person"
    assert event.confidence == pytest.approx(0.45)  # best score, not the last one


# --- degraded mode (hardware unavailable) ------------------------------------


def _fake_hardware_modules(monkeypatch, *, pir, camera, detector):
    monkeypatch.setitem(
        sys.modules, "modules.entry_monitor.sensors.pir_sensor", SimpleNamespace(PIRSensor=pir)
    )
    monkeypatch.setitem(
        sys.modules, "modules.entry_monitor.vision.frame_capture", SimpleNamespace(FrameCapture=camera)
    )
    monkeypatch.setitem(
        sys.modules, "modules.entry_monitor.vision.detector", SimpleNamespace(PersonDetector=detector)
    )


def _raiser(error):
    def factory(*_args, **_kwargs):
        raise error

    return factory


@pytest.mark.parametrize(
    "error",
    [RuntimeError("GPIO busy"), OSError("camera busy"), ValueError("bad model")],
    ids=["gpio-busy", "camera-busy", "bad-model"],
)
def test_constructor_failures_leave_module_degraded_not_crashed(monkeypatch, error):
    _fake_hardware_modules(
        monkeypatch, pir=_raiser(error), camera=_raiser(error), detector=_raiser(error)
    )
    module = em.EntryMonitorModule(Mock())

    assert module._pir is None and module._camera is None and module._detector is None
    module.start()  # must not raise
    module.stop()  # must not raise


def test_degraded_start_does_not_arm_the_pir_it_did_get(monkeypatch):
    """PIR initialised but the camera did not: arming the PIR would produce
    events nobody can confirm, so start() must leave it unarmed."""
    _fake_hardware_modules(
        monkeypatch,
        pir=lambda **_kwargs: FakePIR(),
        camera=_raiser(RuntimeError("camera busy")),
        detector=lambda: ScriptedDetector((True, 0.9)),
    )
    module = em.EntryMonitorModule(Mock())
    assert module._pir is not None and module._camera is None

    module.start()
    assert module._pir.callback is None


def test_missing_hardware_packages_are_tolerated(monkeypatch):
    """ModuleNotFoundError (e.g. no gpiozero on a laptop) is also degraded mode."""
    for name in (
        "modules.entry_monitor.sensors.pir_sensor",
        "modules.entry_monitor.vision.frame_capture",
        "modules.entry_monitor.vision.detector",
    ):
        monkeypatch.setitem(sys.modules, name, None)  # makes `import` raise ImportError

    module = em.EntryMonitorModule(Mock())
    assert module._pir is None and module._camera is None and module._detector is None
    module.start()


# --- FrameCapture edge cases not covered by test_camera_cleanup.py -----------


@pytest.fixture
def capture(monkeypatch):
    camera = Mock()
    monkeypatch.setitem(sys.modules, "picamera2", SimpleNamespace(Picamera2=lambda: camera))
    frame_capture = importlib.import_module("modules.entry_monitor.vision.frame_capture")
    monkeypatch.setattr(frame_capture, "Picamera2", lambda: camera)
    return frame_capture.FrameCapture((640, 480)), camera


def test_closed_capture_cannot_be_restarted(capture):
    wrapper, camera = capture
    wrapper.start()
    wrapper.stop()
    with pytest.raises(RuntimeError, match="closed"):
        wrapper.start()
    assert camera.start.call_count == 1


def test_capture_frame_starts_the_camera_lazily_and_only_once(capture):
    wrapper, camera = capture
    wrapper.capture_frame()
    wrapper.capture_frame()
    camera.start.assert_called_once()
    assert camera.capture_array.call_count == 2


def test_stop_without_start_still_releases_the_device(capture):
    wrapper, camera = capture
    wrapper.stop()
    camera.stop.assert_not_called()
    camera.close.assert_called_once()
