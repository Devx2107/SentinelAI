"""TFLite MobileNet-SSD person detector.

Loads a quantized MobileNet-SSD (COCO-trained) model via ai-edge-litert
and exposes a single `detect_person(frame)` method used by the
entry_monitor module. Kept deliberately narrow — this only answers
"is there a person in this frame, and with what confidence", not
general object detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from ai_edge_litert.interpreter import Interpreter

from config import config

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    person_detected: bool
    confidence: float


class PersonDetector:
    """Runs person detection on a single frame using TFLite MobileNet-SSD."""

    def __init__(self) -> None:
        self._interpreter = Interpreter(model_path=config.vision.model_path)
        self._interpreter.allocate_tensors()

        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()
        _, self._input_height, self._input_width, _ = self._input_details[0]["shape"]

        self._labels = self._load_labels(config.vision.labels_path)
        self._person_class_id = self._labels.index(config.vision.person_label)

    @staticmethod
    def _load_labels(labels_path: str) -> list[str]:
        with open(labels_path, "r") as f:
            return [line.strip() for line in f.readlines()]

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        import cv2  # local import: only needed for resizing, keeps module import light

        resized = cv2.resize(frame, (self._input_width, self._input_height))
        return np.expand_dims(resized, axis=0).astype(np.uint8)

    def detect_person(self, frame: np.ndarray) -> DetectionResult:
        """Run inference on a frame and return whether a person was found."""
        input_tensor = self._preprocess(frame)
        self._interpreter.set_tensor(self._input_details[0]["index"], input_tensor)
        self._interpreter.invoke()

        # Standard TFLite SSD output ordering: boxes, classes, scores, count.
        classes = self._interpreter.get_tensor(self._output_details[1]["index"])[0]
        scores = self._interpreter.get_tensor(self._output_details[2]["index"])[0]

        best_confidence = 0.0
        for class_id, score in zip(classes, scores):
            if int(class_id) == self._person_class_id:
                best_confidence = max(best_confidence, float(score))

        person_detected = best_confidence >= config.vision.confidence_threshold
        logger.debug("Detection result: person=%s confidence=%.2f", person_detected, best_confidence)
        return DetectionResult(person_detected=person_detected, confidence=best_confidence)
