"""One entrypoint: demo on a laptop, checked live startup on a Raspberry Pi."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_env(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or not key.strip().startswith('SENTINELAI_'):
            raise ValueError('Configuration must contain SENTINELAI_NAME=value lines.')
        os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


def preflight():
    checks = []
    def add(name, ok, detail): checks.append(dict(name=name, ok=bool(ok), detail=detail))
    add('dashboard_build', (ROOT/'hub/static/dashboard/index.html').is_file(), 'Prebuilt dashboard must be present.')
    user, password = os.getenv('SENTINELAI_DASHBOARD_USER'), os.getenv('SENTINELAI_DASHBOARD_PASSWORD')
    add('credentials', user and password and password not in ('dev', 'change-me'), 'Set non-default dashboard credentials in .env.')
    for name, default, minimum, maximum in (
        ('HTTP_PORT', '5000', 1, 65535), ('MQTT_PORT', '1883', 1, 65535),
        ('STALE_AFTER_SECONDS', '90', 1, 86400),
        ('RFID_SPI_PORT', '0', 0, 1), ('RFID_SPI_DEVICE', '0', 0, 2),
        ('RFID_RESET_PIN', '25', 0, 27),
    ):
        try:
            value = int(os.getenv('SENTINELAI_' + name, default))
            valid = minimum <= value <= maximum
        except ValueError:
            valid = False
        add(name.lower(), valid, f'Set an integer from {minimum} to {maximum}.')
    for name, default, minimum, maximum in (
        ('CONFIDENCE_THRESHOLD', '0.5', 0, 1),
        ('RFID_AUTH_WINDOW_SECONDS', '30', .1, 86400),
    ):
        try:
            value = float(os.getenv('SENTINELAI_' + name, default))
            valid = math.isfinite(value) and minimum <= value <= maximum
        except ValueError:
            valid = False
        add(name.lower(), valid, f'Set a finite number from {minimum} to {maximum}.')
    for name, default in (('HTTP_HOST', '0.0.0.0'), ('MQTT_HOST', 'localhost'), ('NODE_ID', 'hub')):
        value = os.getenv('SENTINELAI_' + name, default)
        valid = bool(value) and not any(c.isspace() for c in value)
        if name == 'NODE_ID':
            valid = bool(re.fullmatch(r'[A-Za-z0-9_-]+', value))
        add(name.lower(), valid, 'Use a non-empty host or a node ID containing letters, digits, underscores and hyphens.')
    factory = os.getenv('SENTINELAI_RFID_READER_FACTORY', '')
    add('rfid_reader_factory', not factory or bool(re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', factory)), 'Optional reader factory must use module.path:callable syntax.')
    for dependency in ('flask', 'paho', 'gpiozero', 'picamera2', 'ai_edge_litert', 'cv2'):
        add(dependency, importlib.util.find_spec(dependency) is not None, 'Required live dependency.')
    for variable in ('SENTINELAI_MODEL_PATH','SENTINELAI_LABELS_PATH'):
        value = os.getenv(variable, '')
        add(variable.lower(), bool(value) and Path(value).is_file(), 'Set an existing model/labels file path.')
    add('database_location', Path(os.environ['SENTINELAI_DB_PATH']).resolve() != (ROOT/'hub/database/sentinelai.db').resolve(), 'Use a separate writable runtime database, not the tracked sample.')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['demo','live'], default='demo')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--check', action='store_true', help='Check live prerequisites without initializing hardware')
    args = parser.parse_args()
    if args.check and args.mode != 'live':
        parser.error('--check requires --mode live')
    try:
        load_env(args.env_file)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.mode == 'live':
        os.environ['SENTINELAI_DB_PATH'] = str(Path(os.getenv('SENTINELAI_DB_PATH', str(ROOT/'data/sentinelai.db'))).resolve())
        checks = preflight()
        if args.check or not all(c['ok'] for c in checks):
            print(json.dumps({'ready':all(c['ok'] for c in checks),'checks':checks}, indent=2))
            return 0 if all(c['ok'] for c in checks) else 1
        host, port = os.getenv('SENTINELAI_HTTP_HOST','0.0.0.0'), int(os.getenv('SENTINELAI_HTTP_PORT','5000'))
        from runtime import start_live
        app, cleanup = start_live()
    else:
        try:
            port = int(os.getenv('SENTINELAI_HTTP_PORT', '5001'))
            if not 1 <= port <= 65535: raise ValueError
        except ValueError:
            parser.error('SENTINELAI_HTTP_PORT must be an integer from 1 to 65535.')
        from dashboard_dev import create_app
        from services.demo_generator import DemoGenerator
        app = create_app()
        generator = DemoGenerator(app.extensions['sentinel_providers'])
        def cleanup():
            try:
                generator.stop()
            finally:
                temp = app.extensions.get('demo_temp_directory')
                if temp: temp.cleanup()
        try:
            generator.start()
        except BaseException:
            cleanup()
            raise
        host = '127.0.0.1'
    def shutdown(*_): raise SystemExit(0)
    try:
        signal.signal(signal.SIGTERM, shutdown)
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        cleanup()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
