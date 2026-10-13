"""Live wiring verified with fake hardware; no Pi packages are installed."""
import dataclasses
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest


@pytest.fixture
def live_env(tmp_path, monkeypatch):
    import config as config_module
    from database import db
    value = dataclasses.replace(config_module.config, database=dataclasses.replace(config_module.config.database, path=str(tmp_path/'live.db')))
    monkeypatch.setattr(config_module, 'config', value)
    monkeypatch.setattr(db, 'config', value)
    monkeypatch.setenv('SENTINELAI_DASHBOARD_USER','admin')
    monkeypatch.setenv('SENTINELAI_DASHBOARD_PASSWORD','test-only-secret')
    monkeypatch.delenv('SENTINELAI_RFID_READER_FACTORY',raising=False)
    return value


def test_live_wiring_uses_one_shared_auth_state_and_no_demo_generator(live_env, monkeypatch):
    from core import module_loader, mqtt_client
    from core.auth_state import RfidAuthState
    from runtime import start_live
    mqtt=Mock(is_connected=True)
    entry=Mock(module_id='entry_monitor')
    loader=Mock(auth_state=RfidAuthState(),_modules=[entry])
    monkeypatch.setattr(mqtt_client,'get_mqtt_client',lambda:mqtt)
    monkeypatch.setattr(module_loader,'ModuleLoader',Mock(return_value=loader))
    app,stop=start_live()
    providers=app.extensions['sentinel_providers']
    assert providers.mode=='live' and providers.connection.current()['mqtt_connected']
    loader.auth_state.authorize('ABCDEF12','Test owner')
    assert providers.auth.current()['card_uid']=='ABCDEF12'
    assert not any('generator' in key for key in app.extensions)
    assert app.test_client().get('/app/').status_code==200
    stop()
    assert not app.extensions['sentinel_heartbeat'].thread.is_alive()
    loader.stop_all.assert_called_once()
    mqtt.disconnect.assert_called_once()


def test_partial_hardware_initialization_rolls_back(live_env,monkeypatch):
    from core import module_loader, mqtt_client
    from runtime import start_live
    mqtt=Mock(is_connected=True)
    loader=Mock(_modules=[Mock(module_id='entry_monitor',_camera=None)])
    monkeypatch.setattr(mqtt_client,'get_mqtt_client',lambda:mqtt)
    monkeypatch.setattr(module_loader,'ModuleLoader',Mock(return_value=loader))
    with pytest.raises(RuntimeError,match='hardware failed'):
        start_live()
    loader.stop_all.assert_called_once()
    mqtt.disconnect.assert_called_once()


def test_loader_closes_allocated_but_unstarted_modules(monkeypatch):
    from core import module_loader
    first,second=Mock(module_id='first'),Mock(module_id='second')
    first.start.side_effect=RuntimeError('Camera failed')
    monkeypatch.setattr(module_loader,'build_modules',lambda *args:[first,second])
    loader=module_loader.ModuleLoader(Mock())
    with pytest.raises(RuntimeError):loader.start_all()
    first.stop.assert_called_once()
    second.stop.assert_called_once()
    loader.stop_all()
    first.stop.assert_called_once()


def test_env_parser_preserves_existing_environment(tmp_path,monkeypatch):
    from run import load_env
    path=tmp_path/'demo.env'
    path.write_text('# comment\nSENTINELAI_NODE_ID="test"\nSENTINELAI_MQTT_HOST=localhost\n',encoding='utf-8')
    monkeypatch.setenv('SENTINELAI_NODE_ID','already-set')
    monkeypatch.delenv('SENTINELAI_MQTT_HOST',raising=False)
    load_env(path)
    assert __import__('os').environ['SENTINELAI_NODE_ID']=='already-set'
    assert __import__('os').environ['SENTINELAI_MQTT_HOST']=='localhost'


def test_authenticated_detections_are_included_in_analytics(tmp_path,monkeypatch):
    from dashboard_dev import create_app
    from services.stats import entry_stats
    from services.overview import overview
    for key in ('SENTINELAI_DB_PATH','SENTINELAI_DASHBOARD_USER','SENTINELAI_DASHBOARD_PASSWORD'):
        monkeypatch.delenv(key,raising=False)
    app=create_app(tmp_path/'stats.db',clock=lambda:datetime(2026,10,13,12,tzinfo=timezone.utc))
    p=app.extensions['sentinel_providers']
    with p.store.connection(write=True) as conn:
        conn.execute('DELETE FROM events')
        for status in ('person_confirmed_authenticated','motion_authenticated'):
            conn.execute('INSERT INTO events (timestamp,node_id,sensor,status,severity,confidence,message) VALUES (?,?,?,?,?,?,?)',('2026-10-13T11:00:00Z','hub','entry_monitor',status,'info',.9,'Authenticated test'))
    result=entry_stats(p)
    assert result['persons_confirmed']==1 and result['motion_no_person']==1
    assert sum(row['person_confirmed'] for row in result['series'])==1
    assert sum(row['count'] for row in result['confidence_histogram'])==1
    assert overview(p)['counts']['persons_confirmed_24h']==1
