# SentinelAI — AI-Powered IoT Operating System

## 🏠 Overview

**SentinelAI** is a modular, distributed IoT operating system for home security, safety, environmental monitoring, and automation — built on a Raspberry Pi 4 hub, Raspberry Pi Zero W edge nodes, and an Arduino Uno peripheral.

Rather than a collection of isolated sensor scripts, SentinelAI is architected as an actual **hub/node system**: a central hub runs core OS services (device registry, event bus, database, dashboard) while lightweight nodes report sensor data over MQTT. New capabilities plug in as self-contained modules without touching the core.

---

## 🎯 Vision

* Home Security (motion, entry monitoring, AI person detection, RFID auth)
* Safety (gas, fire, smoke detection)
* Environmental Monitoring (temperature, humidity)
* Home Automation (irrigation, water tank monitoring)
* Remote Monitoring & Notifications
* A unified dashboard and event log across all of the above

---

## 🏗️ Architecture

SentinelAI is a **hub/node distributed system**, not a single monolithic script:

```
                        ┌─────────────────────────────┐
                        │   RPi 4 — SentinelAI Hub     │
                        │  ┌────────────────────────┐  │
                        │  │ MQTT Broker (mosquitto)│  │
                        │  ├────────────────────────┤  │
                        │  │ Core OS Services:      │  │
                        │  │  - Device Registry     │  │
                        │  │  - Database (SQLite)   │  │
                        │  │  - Dashboard (Flask)   │  │
                        │  ├────────────────────────┤  │
                        │  │ Modules (pluggable):   │  │
                        │  │  - entry_monitor       │  │
                        │  │  - (future modules)    │  │
                        │  └────────────────────────┘  │
                        └───────────┬──────────────────┘
                              MQTT (WiFi/LAN)
                  ┌──────────────────┼──────────────────┐
          ┌───────▼────────┐  ┌──────▼───────┐   ┌──────▼──────┐
          │ RPi 0 W Node 1  │  │ RPi 0 W Node 2│   │ Arduino Uno │
          │ (future)        │  │ (future)      │   │ (future)    │
          └─────────────────┘  └───────────────┘   └─────────────┘
```

**Core design principles:**

- **Hub/node topology** — the hub doesn't hardcode what sensors exist where; nodes register their own capabilities.
- **MQTT transport** from day one, even while everything runs on a single board — this is the actual protocol production IoT platforms use, and it means adding a real second node later is a config change, not a rewrite.
- **Pluggable modules** — every capability (entry monitoring, motion, RFID, environment) implements a common `BaseModule` interface. The module loader starts whatever's registered; core code never needs to change to add a new capability.
- **Sensor abstraction** — every physical sensor driver implements a common `BaseSensor` interface, so swapping or adding hardware never touches business logic.

---

## 📦 Modules

### Phase 1 — Entry Monitoring (PIR + AI Person Detection) 🚧

**Status:** In development

PIR-triggered, camera-confirmed entry monitoring — motion alone doesn't fire an alert; a Pi Camera frame is run through an on-device person-detection model to confirm before logging a high-severity event. This reduces false positives from pets, shadows, or environmental noise.

**Flow:**
```
PIR motion detected
  → Pi Camera captures frames
  → TFLite MobileNet-SSD checks for a person
  → Event logged (person_confirmed / motion_no_person)
  → Published over MQTT
```

**Hardware (Phase 1):**
- Raspberry Pi 4
- PIR Motion Sensor
- Raspberry Pi Camera Module

**Software:**
- Python, Flask, SQLite
- MQTT (mosquitto + paho-mqtt)
- TensorFlow Lite + MobileNet-SSD (quantized, COCO-trained)
- GPIO Zero, picamera2

### Future Modules

- Motion monitoring on RPi 0 W edge nodes (proves the distributed hub/node architecture with real hardware)
- RFID authentication (RC522 module)
- Environmental monitoring (DHT11 — temperature & humidity)
- Water tank / level monitoring
- Gas & fire detection
- Central dashboard (live status, event timeline, analytics)
- Remote monitoring (Telegram alerts, Tailscale)

---

## 🛠️ Tech Stack

**Hardware currently available:**
- Raspberry Pi 4 (hub)
- 2x Raspberry Pi Zero W (future edge nodes)
- Arduino Uno (future peripheral)
- Raspberry Pi Camera Module
- PIR Motion Sensor, Ultrasonic Sensor, Tilt Switch
- RC522 RFID Module
- DHT11 Temperature/Humidity Sensor
- Water Level Sensor, Sound Sensor
- MPU6050, 5V Relay, Servo/Stepper motors, LCD/7-segment displays
- (Full parts inventory tracked separately — see `/docs`)

**Software:**
- Python, Flask, SQLite
- MQTT (mosquitto broker, paho-mqtt client)
- TensorFlow Lite (ai-edge-litert), OpenCV, picamera2
- GPIO Zero
- HTML, CSS, JavaScript (dashboard, once backend is proven)

---

## 📂 Repository Structure

```
SentinelAI/
├── hub/                          # Runs on the RPi 4
│   ├── app.py                     # Entrypoint — wires DB, MQTT, modules, Flask
│   ├── config.py                   # All configuration in one place
│   ├── core/
│   │   ├── mqtt_client.py           # MQTT wrapper (LWT, pub/sub)
│   │   ├── device_registry.py        # Tracks online nodes + capabilities
│   │   └── module_loader.py           # Starts/stops all registered modules
│   ├── modules/                    # Pluggable capabilities
│   │   ├── base_module.py            # Interface every module implements
│   │   └── entry_monitor/             # Phase 1: PIR + camera + person detection
│   ├── database/                    # SQLite models (events, devices)
│   ├── routes/                      # Dashboard/API routes (Phase 2+)
│   ├── templates/, static/           # Dashboard UI (Phase 2+)
│   └── tests/
├── shared/                        # Code shared between hub and future node agents
│   ├── base_sensor.py               # Interface every sensor driver implements
│   ├── mqtt_topics.py                 # Single source of truth for topic naming
│   └── schemas.py                      # MQTT message payload formats
├── docker-compose.yml              # Runs the mosquitto broker
├── mosquitto/                      # Broker config
├── README.md
└── LICENSE
```

---

## Development and verification

Run commands below from the repository root. Backend tests need neither a
Raspberry Pi nor a running MQTT broker:

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r hub/requirements-dev.txt
python -m pytest -q
```

The suite covers event persistence, MQTT reconnection and shutdown, module
startup rollback, and the health endpoint. Vision tests skip when optional
vision dependencies or model files are absent. GitHub Actions runs the
hardware-free suite on Python 3.11 and 3.12.

To run the full hub on a configured Raspberry Pi, install
`hub/requirements.txt` in an environment with the Pi camera/GPIO system
dependencies available. Supply a compatible quantized MobileNet-SSD TFLite
model and matching labels using `SENTINELAI_MODEL_PATH` and
`SENTINELAI_LABELS_PATH`. These assets are not included. Labels must match
the model's class indices, including any background entry.

```sh
docker compose up -d
python hub/app.py
```

`GET http://localhost:5000/api/health` reports process liveness; it does not
certify sensor readiness or broker connectivity. The current HTTP service
only exposes this endpoint; the dashboard remains planned.

Configuration environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SENTINELAI_MQTT_HOST` | `localhost` | MQTT broker hostname |
| `SENTINELAI_MQTT_PORT` | `1883` | MQTT broker port |
| `SENTINELAI_NODE_ID` | `hub` | Node identity in messages |
| `SENTINELAI_DB_PATH` | `hub/database/sentinelai.db` | SQLite file (relative paths resolve from the working directory) |
| `SENTINELAI_MODEL_PATH` | Model directory under `hub/modules/entry_monitor/vision/` | TFLite model file |
| `SENTINELAI_LABELS_PATH` | Same model directory | Matching labels file |
| `SENTINELAI_CONFIDENCE_THRESHOLD` | `0.5` | Person detection threshold |

---

# 🤝 Contributing

SentinelAI is being developed incrementally, module by module, with hardware brought online one phase at a time. Contributions, suggestions, and feature requests are welcome.

---

# 📜 License

This project is licensed under the MIT License.
