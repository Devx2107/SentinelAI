"""Hardware-free dashboard API. Run from the repo root: python hub/dashboard_dev.py."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Flask

from api.v1 import api_v1
from api.ui import ui_bp
from services.common import Store, integer, utcnow
from services.providers import DatabaseEventSource, DemoAuthWindow, DemoConnectionStatus, Providers
from tools.seed_demo_data import seed_demo_data


def create_app(database_path=None, *, clock=utcnow, seed=True):
    app = Flask(__name__, static_folder=None)
    path = database_path or os.getenv('SENTINELAI_DB_PATH')
    if path is None:
        temporary = TemporaryDirectory(prefix='sentinelai-demo-')
        app.extensions['demo_temp_directory'] = temporary
        path = Path(temporary.name) / 'demo.db'
    path = Path(path).resolve()
    if path == (Path(__file__).resolve().parent / 'database' / 'sentinelai.db'):
        raise ValueError('Refusing to open the committed hub database in the demo runner.')
    if seed:
        seed_demo_data(path, now=clock())
    elif not path.is_file():
        raise ValueError('An existing test database is required with seed=False.')
    store = Store(path)
    app.extensions['sentinel_providers'] = Providers(
        store=store, auth=DemoAuthWindow(clock), connection=DemoConnectionStatus(clock()),
        events=DatabaseEventSource(store), node_id=os.getenv('SENTINELAI_NODE_ID', 'hub'),
        stale_after_seconds=integer(os.getenv('SENTINELAI_STALE_AFTER_SECONDS', '90'), 'stale_after_seconds', maximum=86400),
        clock=clock,
    )
    app.config.update(DASHBOARD_USER=os.getenv('SENTINELAI_DASHBOARD_USER', 'admin'),
                      DASHBOARD_PASSWORD=os.getenv('SENTINELAI_DASHBOARD_PASSWORD', 'dev'))
    app.register_blueprint(api_v1)
    app.register_blueprint(ui_bp)
    return app


if __name__ == '__main__':
    app = create_app()
    from services.demo_generator import DemoGenerator
    generator = DemoGenerator(app.extensions['sentinel_providers'])
    generator.start()
    try:
        app.run(host='127.0.0.1', port=5001, threaded=True, use_reloader=False)
    finally:
        generator.stop()
        temporary = app.extensions.get('demo_temp_directory')
        if temporary:
            temporary.cleanup()
