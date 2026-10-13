"""One entrypoint: demo on a laptop, checked live startup on a Raspberry Pi."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
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
    load_env(args.env_file)
    if args.mode == 'live':
        os.environ['SENTINELAI_DB_PATH'] = str(Path(os.getenv('SENTINELAI_DB_PATH', str(ROOT/'data/sentinelai.db'))).resolve())
        checks = preflight()
        if args.check or not all(c['ok'] for c in checks):
            print(json.dumps({'ready':all(c['ok'] for c in checks),'checks':checks}, indent=2))
            return 0 if all(c['ok'] for c in checks) else 1
        from runtime import start_live
        app, cleanup = start_live()
        host, port = os.getenv('SENTINELAI_HTTP_HOST','0.0.0.0'), int(os.getenv('SENTINELAI_HTTP_PORT','5000'))
    else:
        from dashboard_dev import create_app
        from services.demo_generator import DemoGenerator
        app = create_app()
        generator = DemoGenerator(app.extensions['sentinel_providers'])
        generator.start()
        def cleanup():
            generator.stop()
            temp = app.extensions.get('demo_temp_directory')
            if temp: temp.cleanup()
        host, port = '127.0.0.1', int(os.getenv('SENTINELAI_HTTP_PORT','5001'))
    def shutdown(*_): raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        cleanup()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
