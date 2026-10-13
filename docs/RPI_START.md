# Raspberry Pi handoff

The dashboard is prebuilt in `hub/static/dashboard`. The Pi needs no Node.js
or frontend build. `hub/run.py` is the shared entrypoint; the live runtime
wires the same API and UI to real SQLite, MQTT, PIR/camera and RFID services.
Dashboard v1 remains at `/dashboard`; v2 is at `/app/`.

## Try the complete software on your laptop

From the dashboard checkout:

```powershell
.\.venv\Scripts\python hub/run.py --mode demo
```

Open `http://127.0.0.1:5001/app/`. Standalone demo credentials are `admin` /
`dev`. The producer records an event every four seconds, refreshes online
devices and periodically opens a 30-second RFID authorization window.
Demo card edits affect only a temporary database and reset after shutdown.
Never point the demo at your real database; existing paths are refused.

## One-time Pi setup

Use Raspberry Pi OS with a working camera stack. Install the system hardware
packages and broker, then create an environment that can access those packages:

```bash
sudo apt update
sudo apt install python3-venv python3-picamera2 python3-gpiozero python3-opencv python3-numpy mosquitto
cd /path/to/SentinelAI
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r deploy/requirements-live.txt
cp deploy/sentinelai.env.example .env
```

The `ai-edge-litert` package must have a wheel compatible with your Pi OS
architecture/Python version. The existing all-in-one `hub/requirements.txt`
also pins NumPy 1.26.4; use the split live requirements above with OS packages
to avoid replacing the Pi camera's system NumPy stack. The laptop test setup
uses Python 3.11 and the existing NumPy pin.

Configure `.env` with your broker address, non-default dashboard password,
and absolute model/labels paths. Shell environment variables take precedence.
The parser accepts literal `SENTINELAI_NAME=value` lines and optional surrounding
quotes; it does not evaluate shell expressions. Keep the file private.

Supply a compatible quantized MobileNet-SSD model and matching labels. They
are intentionally not downloaded or committed. Verify their class-index
mapping before relying on person detection. The default runtime database is
`data/sentinelai.db`, created on first live startup; the tracked sample is
refused by the new launcher.

Enable SPI on the Pi and check the camera independently. Default wiring uses
PIR GPIO4; the built-in RC522 adapter uses SPI0/CE0 and reset GPIO25. RC522
connections on a standard 40-pin header:

| RC522 | Raspberry Pi |
| --- | --- |
| 3.3V | Physical pin 1 (3.3V) |
| GND | Physical pin 6 |
| SDA / SS | GPIO8 / CE0, physical pin 24 |
| SCK | GPIO11, physical pin 23 |
| MOSI | GPIO10, physical pin 19 |
| MISO | GPIO9, physical pin 21 |
| RST | GPIO25, physical pin 22 |
| IRQ | Unused |

Power the RC522 at **3.3V**. Set `SENTINELAI_RFID_SPI_PORT`,
`SENTINELAI_RFID_SPI_DEVICE` and `SENTINELAI_RFID_RESET_PIN` to match alternate
wiring. The example enables the built-in adapter with
`SENTINELAI_RFID_READER_FACTORY=modules.rfid_auth.rc522:create_reader`.
Comment it out to run without RFID; System will explicitly show the reader
as unavailable. Alternative adapters may expose the same reader factory.

The driver follows the [NXP MFRC522 register definitions](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf),
[NXP UID cascade flow](https://www.nxp.com/docs/en/application-note/AN10927.pdf)
and [GPIO Zero's SPI interface](https://gpiozero.readthedocs.io/en/rtd/_modules/gpiozero/spi_devices.html).
It reads 4/7/10-byte UIDs, rejects collisions/corrupt replies and emits once
per presentation. UID recognition is not cryptographic proof of identity.
No card contents or keys are written. Protocol tests use a fake bus; physical
RC522 scans remain to be verified on your device.

## Check, connect, start

```bash
.venv/bin/python hub/run.py --mode live --check
.venv/bin/python hub/run.py --mode live
```

`--check` reports software prerequisites without initializing GPIO/camera.
It must exit 0 before live startup. The launch then waits for the MQTT broker
acknowledgment, initializes the reader, camera and detector, and serves the
dashboard. Startup fails with a useful message when mandatory hardware
initialization fails; opened services are cleaned up.

Open `http://<pi-ip>:5000/app/` from your phone or laptop and sign in with
your configured credentials. Inspect System readiness, trigger PIR and tap a
registered card. The live runner never starts the synthetic demo producer.
The included threaded Flask service is intended for a trusted local network;
internet exposure, TLS termination and remote access are outside this handoff.

For boot startup, `deploy/sentinelai.service` is a template. Adjust its User,
WorkingDirectory and ExecStart to your checkout and service account. That
account needs access to the GPIO/SPI/camera devices and writable data directory.
Install the unit only after the foreground command works. Nothing has been
installed or changed on the Pi by this task.

## What still requires the Pi

- OS packages, model/labels, credentials and actual sensor wiring.
- Real camera inference and RC522 scans; validate reader/model compatibility.
- A long-running phone/LAN session, device disconnects and boot-service checks.
- CPU/memory measurements and SQLite contention on the target Pi/storage.

All dashboard pages, REST, streams, card management and live provider wiring
are implemented off-device. Hardware-specific results are deliberately not
claimed from laptop tests.
