"""Central configuration for the SentinelAI hub.

All hardcoded values (GPIO pins, MQTT broker details, database path,
vision model settings) live here. No other module should hardcode
these — import from this module instead.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GPIOConfig:
    """GPIO pin assignments for hub-local sensors (Phase 1: PIR)."""

    pir_pin: int = 4


@dataclass(frozen=True)
class MQTTConfig:
    """Connection settings for the MQTT broker (mosquitto)."""

    broker_host: str = os.getenv("SENTINELAI_MQTT_HOST", "localhost")
    broker_port: int = int(os.getenv("SENTINELAI_MQTT_PORT", "1883"))
    keepalive_seconds: int = 60
    client_id: str = "sentinelai-hub"


@dataclass(frozen=True)
class DatabaseConfig:
    """SQLite database settings."""

    path: str = os.getenv(
        "SENTINELAI_DB_PATH",
        os.path.join(os.path.dirname(__file__), "database", "sentinelai.db"),
    )


@dataclass(frozen=True)
class VisionConfig:
    """TFLite + MobileNet-SSD person-detection settings."""

    model_path: str = os.getenv(
        "SENTINELAI_MODEL_PATH",
        os.path.join(
            os.path.dirname(__file__),
            "modules",
            "entry_monitor",
            "vision",
            "models",
            "mobilenet_ssd_v2_coco_quant.tflite",
        ),
    )
    labels_path: str = os.getenv(
        "SENTINELAI_LABELS_PATH",
        os.path.join(
            os.path.dirname(__file__),
            "modules",
            "entry_monitor",
            "vision",
            "models",
            "coco_labels.txt",
        ),
    )
    person_label: str = "person"
    confidence_threshold: float = float(
        os.getenv("SENTINELAI_CONFIDENCE_THRESHOLD", "0.5")
    )
    capture_resolution: tuple[int, int] = (640, 480)
    # How long to keep sampling frames after a PIR trigger before giving up
    # on finding a person (helps with slow-to-enter-frame subjects).
    capture_window_seconds: float = 3.0
    frames_per_capture_window: int = 3


@dataclass(frozen=True)
class NodeConfig:
    """Identity of this device on the SentinelAI network."""

    node_id: str = os.getenv("SENTINELAI_NODE_ID", "hub")


@dataclass(frozen=True)
class Config:
    gpio: GPIOConfig = field(default_factory=GPIOConfig)
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    node: NodeConfig = field(default_factory=NodeConfig)


config = Config()
