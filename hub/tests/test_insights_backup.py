import base64
from datetime import datetime, timedelta, timezone
import sqlite3
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from dashboard_dev import create_app
from services.common import iso, ServiceError
from services.backup import create_backup

NOW=datetime(2026,10,13,12,tzinfo=timezone.utc)
AUTH={'Authorization':'Basic '+base64.b64encode(b'admin:dev').decode()}


@pytest.fixture
def app(tmp_path,monkeypatch):
    for key in ('SENTINELAI_DB_PATH','SENTINELAI_DASHBOARD_USER','SENTINELAI_DASHBOARD_PASSWORD','SENTINELAI_NODE_ID','SENTINELAI_STALE_AFTER_SECONDS'):
        monkeypatch.delenv(key,raising=False)
    return create_app(tmp_path/'features.db',clock=lambda:NOW)


def test_insights_hour_boundaries_and_previous_day(app):
    p=app.extensions['sentinel_providers']
    rows=[(30*60,'warning','rfid_auth','card_denied'),(59*60,'critical','entry_monitor','person_confirmed'),
          (3600,'critical','entry_monitor','person_confirmed'),(3601,'warning','entry_monitor','person_confirmed'),
          (25*3600,'info','entry_monitor','motion_no_person'),(24*3600,'info','entry_monitor','motion_no_person'),
          (0,'critical','entry_monitor','person_confirmed'),(48*3600,'info','entry_monitor','motion_no_person'),
          (48*3600+1,'info','entry_monitor','motion_no_person')]
    with p.store.connection(write=True) as conn:
        conn.execute('DELETE FROM events')
        for seconds,severity,sensor,status in rows:
            conn.execute('INSERT INTO events (timestamp,node_id,sensor,status,severity,message) VALUES (?,?,?,?,?,?)',
                (iso(NOW-timedelta(seconds=seconds)),'hub',sensor,status,severity,'Test'))
    response=app.test_client().get('/api/v1/insights',headers=AUTH)
    assert response.status_code==200
    result=response.json
    assert result['recent']==dict(warnings_1h=1,critical_1h=2,cards_denied_1h=1)
    assert result['comparison']==dict(current=5,previous=2,difference=3,percent_change=150.0)
    assert result['top_devices'][0]==dict(node_id='hub',events=5,attention_events=4)
    assert next(a for a in result['alerts'] if a['id']=='recent-critical')['href'].startswith('/events?severity=critical&since=')


def test_insights_empty_baseline_and_live_connection_alert(app):
    p=app.extensions['sentinel_providers']
    with p.store.connection(write=True) as conn:
        conn.execute('DELETE FROM events')
        conn.execute('DELETE FROM devices')
    client=app.test_client()
    result=client.get('/api/v1/insights',headers=AUTH).json
    assert result['comparison']['percent_change'] is None
    assert result['alerts']==[] and result['top_devices']==[]
    p.mode='live'
    p.connection=SimpleNamespace(current=lambda:{'mqtt_connected':False})
    assert client.get('/api/v1/insights',headers=AUTH).json['alerts'][0]['id']=='mqtt-disconnected'
    assert client.get('/api/v1/insights').status_code==401


def test_backup_auth_and_snapshot_integrity(app,tmp_path):
    client=app.test_client()
    assert client.get('/api/v1/backup').status_code==401
    response=client.get('/api/v1/backup',headers=AUTH)
    assert response.status_code==200
    assert response.headers['Cache-Control']=='no-store'
    assert response.headers['Content-Disposition'].startswith('attachment; filename="sentinelai-hub-')
    assert response.data.startswith(b'SQLite format 3\x00')
    restored=tmp_path/'restored.sqlite3'
    restored.write_bytes(response.data)
    with sqlite3.connect(restored) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]==800
        assert conn.execute('SELECT COUNT(*) FROM known_cards').fetchone()[0]==4
    response.close()


def test_backup_cap_disconnect_cleanup_and_stable_snapshot(app,tmp_path,monkeypatch):
    import api.backup as module
    original=module.create_backup
    paths=[]
    def tracked(store):
        path,close=original(store)
        paths.append(path)
        return path,close
    monkeypatch.setattr(module,'create_backup',tracked)
    client=app.test_client()
    first=client.get('/api/v1/backup',headers=AUTH,buffered=False)
    assert paths[0].exists()
    assert client.get('/api/v1/backup',headers=AUTH).status_code==503
    with app.extensions['sentinel_providers'].store.connection(write=True) as conn:
        conn.execute("INSERT INTO events (timestamp,node_id,sensor,status,severity,message) VALUES ('2026-10-13T11:59:00Z','hub','test','ok','info','After snapshot')")
    restored=tmp_path/'snapshot.sqlite3'
    restored.write_bytes(b''.join(first.response))
    with sqlite3.connect(restored) as conn:
        assert conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]==800
    first.close()
    assert not paths[0].exists()
    second=client.get('/api/v1/backup',headers=AUTH,buffered=False)
    second.close()  # Abort before reading the remaining body.
    assert not paths[1].exists()


def test_backup_failure_releases_slot(app,tmp_path):
    p=app.extensions['sentinel_providers']
    original=p.store.path
    p.store.path=tmp_path/'missing.db'
    assert app.test_client().get('/api/v1/backup',headers=AUTH).status_code==503
    p.store.path=original
    response=app.test_client().get('/api/v1/backup',headers=AUTH)
    assert response.status_code==200
    response.close()
    with pytest.raises(ServiceError,match='busy'):
        create_backup(p.store,timeout_seconds=-1)


def test_hub_heartbeat_refreshes_local_state_and_reuses_wire_contract():
    from services.hub_heartbeat import HubHeartbeat
    from shared.schemas import HeartbeatPayload
    mqtt,refresh=Mock(),Mock()
    heartbeat=HubHeartbeat(mqtt,refresh,'hub',clock=lambda:NOW,interval=60)
    heartbeat.tick()
    refresh.assert_called_once()
    topic,payload=mqtt.publish.call_args.args
    assert topic=='sentinelai/hub/heartbeat'
    decoded=HeartbeatPayload.from_json(payload)
    assert decoded.node_id=='hub' and decoded.timestamp==iso(NOW)
    assert decoded.uptime_seconds>=0
    heartbeat.start()
    assert heartbeat.thread.is_alive()
    heartbeat.stop()
    assert not heartbeat.thread.is_alive()
