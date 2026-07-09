"""Standalone sanity check for the entry_monitor TFLite person detector.

This does NOT touch PIR or the Pi Camera -- it only verifies that the
TFLite model + labels file are correctly in place and that
PersonDetector can load them and run a single inference pass. Meant to
be run on the Pi (or any machine with ai-edge-litert + opencv installed)
as an isolated checkpoint before wiring up the rest of the pipeline.

Skips automatically if the model/labels files aren't present locally,
since they're git-ignored binaries downloaded separately rather than
committed to the repo (see README).
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import config  # noqa: E402

pytest.importorskip("ai_edge_litert")
pytest.importorskip("cv2")

_MODEL_MISSING = not os.path.exists(config.vision.model_path)
_LABELS_MISSING = not os.path.exists(config.vision.labels_path)

pytestmark = pytest.mark.skipif(
    _MODEL_MISSING or _LABELS_MISSING,
    reason=(
        "Model/labels file not found locally. These are git-ignored binaries "
        "downloaded separately (see README) -- this test only runs where "
        "they've been placed, e.g. on the Pi itself."
    ),
)


@pytest.fixture(scope="module")
def detector():
    from modules.entry_monitor.vision.detector import PersonDetector

    return PersonDetector()


def test_model_and_labels_load(detector):
    """Confirms the interpreter initialized, the labels file parsed, and
    'person' resolved to a valid class index -- i.e. the model + labels
    pairing is correct, not just present.
    """
    assert detector._person_class_id >= 0
    assert "person" in detector._labels


def test_detect_person_on_blank_frame(detector):
    """A blank frame should run through the full pipeline without error
    and return a well-formed DetectionResult. This doesn't assert a
    person IS or ISN'T detected -- a blank frame's actual result depends
    on model noise -- it only proves the model, preprocessing, and output
    parsing all work end-to-end.
    """
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detector.detect_person(frame)

    assert isinstance(result.person_detected, bool)
    assert 0.0 <= result.confidence <= 1.0


def test_detect_person_on_random_noise_frame(detector):
    """Random noise shouldn't crash the pipeline either. Not a hard
    guarantee on confidence being low, just another real inference pass
    with different input statistics than an all-zero frame.
    """
    rng = np.random.default_rng(seed=42)
    frame = rng.integers(0, 256, size=(480, 640, 3), dtype=np.uint8)
    result = detector.detect_person(frame)

    assert isinstance(result.person_detected, bool)
    assert 0.0 <= result.confidence <= 1.0
