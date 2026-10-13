"""Live wiring, separate from the hardware-free dashboard import graph."""
import importlib
import os
import time
from services.common import Store, utcnow, integer
from services.providers import Providers, LiveAuthWindow, LiveConnectionStatus, DatabaseEventSource
from services.hub_heartbeat import HubHeartbeat


def start_live():
    from flask import Flask
    from api.v1 import api_v1
    from api.ui import ui_bp
    from routes.dashboard import dashboard_bp
    from config import config
    from database.db import init_db
    from core.mqtt_client import get_mqtt_client
    from core.device_registry import DeviceRegistry
    from core.module_loader import ModuleLoader
    init_db()
    mqtt = get_mqtt_client()
    loader = reader = heartbeat = None
    def stop():
        try:
            if heartbeat:
                heartbeat.stop()
        finally:
            try:
                if loader:
                    loader.stop_all()
                elif reader:
                    reader.close()
            finally:
                mqtt.disconnect()
    try:
        mqtt.connect()
        deadline = time.monotonic() + 10
        while not mqtt.is_connected and time.monotonic() < deadline:
            time.sleep(.1)
        if not mqtt.is_connected:
            raise RuntimeError('MQTT broker connection was not acknowledged within 10 seconds.')
        factory = os.getenv('SENTINELAI_RFID_READER_FACTORY')
        if factory:
            module, name = factory.split(':', 1)
            reader = getattr(importlib.import_module(module), name)()
        loader = ModuleLoader(mqtt, reader=reader)
        # The legacy module tolerates missing hardware. Live startup must not silently do so.
        entry = next((m for m in loader._modules if m.module_id == 'entry_monitor'), None)
        if not entry or any(getattr(entry, attr, None) is None for attr in ('_pir', '_camera', '_detector')):
            raise RuntimeError('Entry-monitor hardware failed initialization. Check camera, GPIO, model and labels.')
        loader.start_all()
        registry = DeviceRegistry()
        registry.register_with_mqtt(mqtt)
        capabilities = ['pir', 'camera', 'entry_monitor'] + (['rfid'] if reader else [])
        registry.register_local_device(config.node.node_id, capabilities)
        stale_after = integer(os.getenv('SENTINELAI_STALE_AFTER_SECONDS', '90'), 'stale_after_seconds', maximum=86400)
        heartbeat = HubHeartbeat(mqtt, lambda: registry.register_local_device(config.node.node_id, capabilities),
            config.node.node_id, interval=max(.25, min(30, stale_after / 3)))
        heartbeat.start()
        app = Flask(__name__, template_folder='templates', static_folder='static')
        store = Store(config.database.path)
        app.extensions['sentinel_providers'] = Providers(store, LiveAuthWindow(loader.auth_state),
            LiveConnectionStatus(utcnow(), lambda: mqtt.is_connected), DatabaseEventSource(store), node_id=config.node.node_id,
            mode='live', stale_after_seconds=stale_after)
        app.extensions['sentinel_heartbeat'] = heartbeat
        app.extensions['sentinel_readiness'] = [dict(name='Entry monitor', ok=True, detail='PIR, camera and model initialized.'),
            dict(name='RFID reader', ok=reader is not None, detail='Physical reader adapter loaded.' if reader else 'No physical reader adapter configured; card management is available, scanning is not.')]
        app.extensions['sentinel_reader'] = reader
        app.register_blueprint(api_v1)
        app.register_blueprint(ui_bp)
        app.register_blueprint(dashboard_bp)
        return app, stop
    except BaseException:
        stop()
        raise
