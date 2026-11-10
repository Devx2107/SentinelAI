# SentinelAI — AI-Powered IoT Operating System

## Dashboard v2 — ready for local demo and Pi setup

The responsive dashboard includes live events, device views, RFID card
management, entry analytics, security insights, saved event views, database
backups and system readiness. Its prebuilt UI requires no
Node.js on the Raspberry Pi.

```sh
python hub/run.py --mode demo
```

Open `http://127.0.0.1:5001/app/` with standalone demo credentials `admin` /
`dev`. See [Pi startup instructions](docs/RPI_START.md) and
[dashboard features and development](docs/dashboard-v2-complete.md).

`hub/run.py` is the shared entrypoint:

| Mode | Command | Where |
| --- | --- | --- |
| Demo (no hardware, temporary database) | `python hub/run.py --mode demo` | `http://127.0.0.1:5001/app/` |
| Live prerequisite check (no hardware initialized) | `python hub/run.py --mode live --check` | Prints a readiness report and exits |
| Live (real SQLite, MQTT, PIR/camera, RFID) | `python hub/run.py --mode live` | `http://<pi-ip>:5000/app/` by default |

Dashboard v1 remains available at `/dashboard` in live mode.

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
                        │  │  - Dashboard (Flask +  │  │
                        │  │    React UI)           │  │
                        │  ├────────────────────────┤  │
                        │  │ Modules (pluggable):   │  │
                        │  │  - entry_monitor       │  │
                        │  │  - rfid_auth           │  │
                        │  │  - (future modules)    │  │
                        │  └────────────────────────┘  │
                        └───────────┬──────────────────┘
                              MQTT (WiFi/LAN)
                  ┌──────────────────┼──────────────────┐
          ┌───────▼────────┐  ┌──────▼───────┐   ┌──────▼──────┐
          │ RPi 0 W Node 1  │  │ RPi 0 W Node 2│   │ Arduino Uno │
          │ (node_agent)    │  │ (node_agent)  │   │ (future)    │
          └─────────────────┘  └───────────────┘   └─────────────┘
```

The `node_agent` package (heartbeat and sensor publishing over MQTT) is
implemented and covered by hardware-free tests with simulated sensors.
Deployment on physical Pi Zero W nodes and the Arduino peripheral is still to
come.

**Core design principles:**

- **Hub/node topology** — the hub doesn't hardcode what sensors exist where; nodes register their own capabilities.
- **MQTT transport** from day one, even while everything runs on a single board — this is the actual protocol production IoT platforms use, and it means adding a real second node later is a config change, not a rewrite.
- **Pluggable modules** — every capability (entry monitoring, motion, RFID, environment) implements a common `BaseModule` interface. The module loader starts whatever's registered; core code never needs to change to add a new capability.
- **Sensor abstraction** — every physical sensor driver implements a common `BaseSensor` interface, so swapping or adding hardware never touches business logic.

---

## 📦 Modules

### Phase 1 — Entry Monitoring (PIR + AI Person Detection) 🚧

**Status:** Implemented in software with hardware-free tests. End-to-end
validation on the Pi (PIR, camera and a supplied model) is still pending.

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

### RFID Authentication (RC522) 🚧

**Status:** Implemented in software. Protocol tests use a fake SPI bus; physical
RC522 scans remain to be verified on real hardware.

The `rfid_auth` module reads card UIDs through a reader adapter (a built-in
RC522 driver over SPI, or a simulated reader), checks them against registered
cards and opens a time-limited authorization window. Cards are created,
edited, enabled and disabled from the dashboard's Access page. UID recognition
is not cryptographic proof of identity. See [RPI_START.md](docs/RPI_START.md)
for wiring.

### Dashboard v2 ✅

A React/TypeScript single-page app served by the hub at `/app/`, backed by an
authenticated REST API (`/api/v1`) and a resumable event stream. It covers
live events, devices, access management, entry analytics, security insights,
saved views, database backups and system readiness. Details are in
[docs/dashboard-v2-complete.md](docs/dashboard-v2-complete.md) and
[docs/dashboard-features-2.1.md](docs/dashboard-features-2.1.md). Arm/disarm,
commands, video, user accounts and push notifications are not implemented.

### Future Modules

- Motion monitoring on RPi 0 W edge nodes (proves the distributed hub/node architecture with real hardware)
- Environmental monitoring (DHT11 — temperature & humidity)
- Water tank / level monitoring
- Gas & fire detection
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
- (Full parts inventory tracked separately)

**Software:**
- Python, Flask, SQLite
- MQTT (mosquitto broker, paho-mqtt client)
- TensorFlow Lite (ai-edge-litert), OpenCV, picamera2
- GPIO Zero
- React, TypeScript, Vite, Vitest (dashboard UI; prebuilt output is committed, so Node.js is only needed for UI development)

---

## 📂 Repository Structure

```
SentinelAI/
├── hub/                          # Runs on the RPi 4
│   ├── run.py                     # Entrypoint — demo mode and checked live mode
│   ├── runtime.py                  # Live wiring: MQTT, modules, providers, Flask
│   ├── dashboard_dev.py             # Hardware-free demo app factory
│   ├── app.py                       # Original all-in-one entrypoint (health check, dashboard v1)
│   ├── config.py                    # Hub configuration (environment-driven)
│   ├── api/                       # Dashboard v2 REST API, event stream, auth, backups, UI serving
│   ├── services/                   # Query/aggregation logic and demo generator (no hardware imports)
│   ├── core/
│   │   ├── mqtt_client.py           # MQTT wrapper (LWT, pub/sub)
│   │   ├── device_registry.py        # Tracks online nodes + capabilities
│   │   ├── module_loader.py           # Starts/stops all registered modules
│   │   └── auth_state.py               # Shared RFID authorization window state
│   ├── modules/                    # Pluggable capabilities
│   │   ├── base_module.py            # Interface every module implements
│   │   ├── entry_monitor/             # PIR + camera + person detection
│   │   └── rfid_auth/                  # RC522 adapter, simulated reader, authorization
│   ├── database/                    # SQLite models and queries (events, devices, RFID cards)
│   ├── routes/, templates/           # Dashboard v1, served at /dashboard
│   ├── static/dashboard/              # Prebuilt dashboard v2 (committed)
│   ├── tools/                        # Contract export, demo seeding, database load check
│   └── tests/
├── dashboard-ui/                  # Dashboard v2 source (React, TypeScript, Vite)
├── node_agent/                    # Edge node agent (heartbeat, sensor publishing) and tests
├── shared/                        # Code shared between hub and node agents
│   ├── base_sensor.py               # Interface every sensor driver implements
│   ├── mqtt_topics.py                 # Single source of truth for topic naming
│   └── schemas.py                      # MQTT message payload formats
├── deploy/                        # Pi live requirements, .env example, systemd unit template
├── data/                          # Runtime database location (contents are git-ignored)
├── docs/                          # Pi handoff and dashboard documentation
├── docker-compose.yml              # Runs the mosquitto broker
├── mosquitto/                      # Broker config
├── .github/workflows/              # Backend and dashboard CI workflows
├── pytest.ini
├── README.md
└── LICENSE
```

---

## 📚 Documentation

| Document | Contents |
| --- | --- |
| [docs/RPI_START.md](docs/RPI_START.md) | Raspberry Pi setup, RC522 wiring, check/start commands and what still needs real hardware |
| [docs/dashboard-v2-complete.md](docs/dashboard-v2-complete.md) | Dashboard v2 features, run and maintain, verification scope |
| [docs/dashboard-features-2.1.md](docs/dashboard-features-2.1.md) | Security insights, saved views and database backups |
| [docs/dashboard-v2.md](docs/dashboard-v2.md) | Historical Phase 1 backend notes |
| [docs/dashboard-v2-review.md](docs/dashboard-v2-review.md) | Historical plan review and refinements |

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
startup rollback, the dashboard API and its contract, event streams, insights
and backups, the launcher, RFID authorization and the RC522 protocol, entry
monitor logic and the node agent. Vision tests skip when optional vision
dependencies or model files are absent. GitHub Actions workflows are
configured to run the hardware-free backend suite on Python 3.11 and 3.12 and
the dashboard checks (backend tests, frontend tests and a production build on
Node 22).

### Dashboard UI development

The dashboard source lives in `dashboard-ui/` and needs Node.js 22.21 or newer.
Start the demo API first (`python hub/run.py --mode demo`); Vite proxies `/api`
to port 5001.

```sh
cd dashboard-ui
npm ci
npm run dev
npm test
npm run build
```

`npm run build` writes to `hub/static/dashboard`, which is committed so the Pi
needs no frontend toolchain. Shared API fixtures are regenerated with
`python hub/tools/export_dashboard_contract.py`.

### Running on a Raspberry Pi

Follow [docs/RPI_START.md](docs/RPI_START.md). In outline: install the system
hardware packages and a broker (`docker compose up -d` also starts mosquitto),
install `deploy/requirements-live.txt`, copy `deploy/sentinelai.env.example` to
`.env`, and set non-default dashboard credentials and absolute paths to a
compatible quantized MobileNet-SSD TFLite model and matching labels. These
assets are not included. Labels must match the model's class indices,
including any background entry. Then run:

```sh
python hub/run.py --mode live --check
python hub/run.py --mode live
```

`--check` must report ready before live startup. Hardware-specific behavior
(camera inference, RC522 scans, long-running sessions, performance on Pi
storage) has not been verified on a physical Pi.

`GET /api/v1/health` is an unauthenticated liveness endpoint that also reports
database status; it does not certify sensor readiness or broker connectivity.
Use the dashboard's System page for readiness. The original `hub/app.py`
entrypoint remains available and serves `GET /api/health` and dashboard v1.

### Configuration environment variables

Values may be set in the shell or in a `.env` file at the repository root
(shell variables take precedence). Defaults below are the code defaults;
`deploy/sentinelai.env.example` shows a Pi-oriented starting point.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SENTINELAI_MQTT_HOST` | `localhost` | MQTT broker hostname |
| `SENTINELAI_MQTT_PORT` | `1883` | MQTT broker port |
| `SENTINELAI_NODE_ID` | `hub` (hub), `node-1` (node agent) | Node identity in messages |
| `SENTINELAI_DB_PATH` | `hub/database/sentinelai.db`; `data/sentinelai.db` in live mode | SQLite file (live mode refuses the tracked sample database) |
| `SENTINELAI_MODEL_PATH` | Model directory under `hub/modules/entry_monitor/vision/` | TFLite model file (live mode requires an existing file) |
| `SENTINELAI_LABELS_PATH` | Same model directory | Matching labels file (live mode requires an existing file) |
| `SENTINELAI_CONFIDENCE_THRESHOLD` | `0.5` | Person detection threshold (0 to 1) |
| `SENTINELAI_DASHBOARD_USER` | None | Dashboard Basic-auth user (live mode requires it) |
| `SENTINELAI_DASHBOARD_PASSWORD` | None | Dashboard password; live mode rejects `dev` and `change-me` |
| `SENTINELAI_HTTP_HOST` | `0.0.0.0` (live) | Live HTTP bind address; demo always binds `127.0.0.1` |
| `SENTINELAI_HTTP_PORT` | `5000` (live), `5001` (demo) | HTTP port |
| `SENTINELAI_STALE_AFTER_SECONDS` | `90` | Time without a heartbeat before a device shows as stale |
| `SENTINELAI_RFID_AUTH_WINDOW_SECONDS` | `30` | How long an authorization lasts after a valid card scan |
| `SENTINELAI_RFID_READER_FACTORY` | Unset | Reader adapter as `module.path:callable`; the example uses the built-in RC522 adapter |
| `SENTINELAI_RFID_SPI_PORT` | `0` | SPI port for the RC522 adapter |
| `SENTINELAI_RFID_SPI_DEVICE` | `0` | SPI chip-select device for the RC522 adapter |
| `SENTINELAI_RFID_RESET_PIN` | `25` | RC522 reset GPIO pin |
| `SENTINELAI_HEARTBEAT_INTERVAL` | `10` | Node agent heartbeat interval in seconds |
| `SENTINELAI_MQTT_CLIENT_ID` | `sentinelai-node` | Node agent MQTT client ID |

---

# 🤝 Contributing

SentinelAI is being developed incrementally, module by module, with hardware brought online one phase at a time. Contributions, suggestions, and feature requests are welcome.

---

# 📜 License

This project is licensed under the MIT License.
