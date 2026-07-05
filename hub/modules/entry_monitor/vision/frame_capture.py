"""Pi Camera Module wrapper.

Wraps picamera2 behind a small interface so the detector and module
logic never touch the camera library directly — useful if you ever
swap to a USB webcam or move the camera to a node agent later.
"""

from __future__ import annotations

import logging

import numpy as np
from picamera2 import Picamera2

logger = logging.getLogger(__name__)


class FrameCapture:
    """Captures still frames from the Pi Camera Module on demand."""

    def __init__(self, resolution: tuple[int, int]) -> None:
        self._camera = Picamera2()
        config = self._camera.create_still_configuration(
            main={"size": resolution, "format": "RGB888"}
        )
        self._camera.configure(config)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._camera.start()
            self._started = True
            logger.info("Camera started")

    def capture_frame(self) -> np.ndarray:
        """Capture a single frame as an RGB numpy array."""
        if not self._started:
            self.start()
        return self._camera.capture_array()

    def stop(self) -> None:
        if self._started:
            self._camera.stop()
            self._started = False
            logger.info("Camera stopped")
