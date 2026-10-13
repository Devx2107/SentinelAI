import importlib
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


@pytest.fixture
def capture(monkeypatch):
    camera=Mock()
    monkeypatch.setitem(sys.modules,'picamera2',SimpleNamespace(Picamera2=lambda:camera))
    # Import the wrapper, not the actual optional camera package.
    module=importlib.import_module('modules.entry_monitor.vision.frame_capture')
    monkeypatch.setattr(module,'Picamera2',lambda:camera)
    return module.FrameCapture,camera


def test_camera_configuration_failure_closes_device(capture):
    factory,camera=capture
    camera.configure.side_effect=RuntimeError('configuration failed')
    with pytest.raises(RuntimeError):factory((640,480))
    camera.close.assert_called_once()


def test_camera_stop_closes_even_after_stop_failure(capture):
    factory,camera=capture
    wrapper=factory((640,480))
    wrapper.start()
    camera.stop.side_effect=RuntimeError('stop failed')
    with pytest.raises(RuntimeError):wrapper.stop()
    camera.close.assert_called_once()
    wrapper.stop()
    camera.close.assert_called_once()
