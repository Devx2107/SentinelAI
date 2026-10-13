"""API contract and regression tests using only temporary SQLite databases."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from dashboard_dev import create_app
from services.common import iso
from services.providers import LiveAuthWindow, LiveConnectionStatus
from tools.seed_demo_data import seed_demo_data

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'admin:dev').decode()}


@pytest.fixture
def app(tmp_path, monkeypatch):
    for key in ('SENTINELAI_DB_PATH', 'SENTINELAI_DASHBOARD_USER', 'SENTINELAI_DASHBOARD_PASSWORD', 'SENTINELAI_NODE_ID', 'SENTINELAI_STALE_AFTER_SECONDS'):
        monkeypatch.delenv(key, raising=False)
    result = create_app(tmp_path / 'test.db', clock=lambda: NOW)
    result.config['TESTING'] = True
    return result


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def store(app):
    return app.extensions['sentinel_providers'].store


def get(client, path):
    return client.get('/api/v1' + path, headers=AUTH)


def insert_event(store, *, timestamp=None, sensor='entry_monitor', status='person_confirmed', severity='warning', confidence=0.9, message='Person at entry', node='hub'):
    with store.connection(write=True) as conn:
        return conn.execute('INSERT INTO events (timestamp, node_id, sensor, status, severity, confidence, message) VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (timestamp or iso(NOW - timedelta(seconds=1)), node, sensor, status, severity, confidence, message)).lastrowid


def clear_events(store):
    with store.connection(write=True) as conn:
        conn.execute('DELETE FROM events')


def test_auth_and_public_health(client, app):
    assert client.get('/api/v1/health').status_code == 200
    response = client.get('/api/v1/overview')
    assert response.status_code == 401
    assert response.headers['WWW-Authenticate'].startswith('Basic ')
    assert response.json['error']['code'] == 'unauthorized'
    assert client.get('/api/v1/overview', headers={'Authorization': 'Bearer nope'}).status_code == 401
    assert get(client, '/overview').status_code == 200
    app.config['DASHBOARD_PASSWORD'] = ''
    assert get(client, '/overview').json['error']['code'] == 'auth_not_configured'
    assert get(client, '/overview').status_code == 500


def test_overview_counts_and_auth_expiry(client, store, app):
    clear_events(store)
    insert_event(store)
    insert_event(store, sensor='rfid_auth', status='card_denied', confidence=None)
    insert_event(store, severity='critical')
    insert_event(store, timestamp=iso(NOW - timedelta(days=2)))
    body = get(client, '/overview').json
    assert body['counts'] == dict(devices_total=3, devices_online=2, devices_stale=0, devices_offline=1,
                                  events_24h=3, warnings_24h=2, critical_24h=1, persons_confirmed_24h=2, cards_denied_24h=1)
    assert body['auth_window'] is None
    provider = app.extensions['sentinel_providers'].auth
    provider.set(dict(card_uid='04A1B2C3', card_label='Dev', expires_at=iso(NOW + timedelta(seconds=30))))
    assert get(client, '/overview').json['auth_window']['active'] is True
    provider.clock = lambda: NOW + timedelta(seconds=30)
    assert get(client, '/overview').json['auth_window'] is None


def test_devices_are_read_only_and_stale_logic_is_clock_injected(client, store, app):
    with store.connection(write=True) as conn:
        conn.execute('UPDATE devices SET last_seen = ? WHERE node_id = ?', (iso(NOW - timedelta(seconds=91)), 'node-zero-01'))
    devices = get(client, '/devices').json['devices']
    assert next(d for d in devices if d['node_id'] == 'node-zero-01')['effective_status'] == 'stale'
    detail = get(client, '/devices/hub').json
    assert len(detail['recent_events']) == 20
    assert all(event['node_id'] == 'hub' for event in detail['recent_events'])
    assert get(client, '/devices/unknown').status_code == 404
    assert store.rows("SELECT status FROM devices WHERE node_id = 'node-zero-01'")[0]['status'] == 'online'


@pytest.mark.parametrize('timestamp, expected_age, expected_status', [(None, None, 'stale'), ('bad', None, 'stale'), ('2026-10-13T12:00:05Z', 0, 'online'), ('2026-10-13T11:58:30Z', 90, 'online')])
def test_device_time_edges(client, store, timestamp, expected_age, expected_status):
    with store.connection(write=True) as conn:
        conn.execute("UPDATE devices SET last_seen = ? WHERE node_id = 'hub'", (timestamp,))
    row = get(client, '/devices/hub').json
    assert row['effective_status'] == expected_status
    assert row['seconds_since_seen'] == expected_age


def test_events_cursor_is_stable_and_counts_ignore_cursor(client, store):
    first = get(client, '/events?limit=13').json
    assert len(first['events']) == 13
    insert_event(store)
    second = get(client, f"/events?limit=13&cursor={first['next_cursor']}").json
    assert {e['id'] for e in first['events']}.isdisjoint(e['id'] for e in second['events'])
    assert second['total_matching'] == 801
    last = get(client, '/events?cursor=2').json
    assert len(last['events']) == 1 and last['next_cursor'] is None


def test_filters_mixed_timezones_and_literal_search(client, store):
    clear_events(store)
    kept = insert_event(store, timestamp='2026-10-13T16:30:00+05:30', message='Test 100%_safe', severity='critical')
    insert_event(store, timestamp='2026-10-13T11:00:00Z', sensor='rfid_auth')
    insert_event(store, timestamp='2026-10-13T12:00:00+00:00')
    response = client.get('/api/v1/events', headers=AUTH, query_string=dict(sensor='entry_monitor', node_id='hub', severity='critical,warning', status='person_confirmed', since='2026-10-13T11:00:00Z', until='2026-10-13T12:00:00Z', q='100%_SAFE'))
    assert [e['id'] for e in response.json['events']] == [kept]
    assert get(client, '/events?q=does-not-exist').json['total_matching'] == 0


@pytest.mark.parametrize('key', ['q', 'sensor', 'node_id', 'severity', 'status'])
def test_injection_is_inert(client, store, key):
    response = client.get('/api/v1/events', headers=AUTH, query_string={key: "x' OR 1=1; DROP TABLE events;--"})
    assert response.status_code == 200
    assert response.json['events'] == []
    assert store.rows('SELECT COUNT(*) AS n FROM events')[0]['n'] == 800


@pytest.mark.parametrize('query', ['limit=0', 'limit=201', 'limit=no', 'cursor=-1', 'cursor=1.5', 'since=bad', 'since=2026-10-13', 'since=2026-10-14T00:00:00Z&until=2026-10-13T00:00:00Z', 'severity=,,,'])
def test_invalid_event_filters_are_400(client, query):
    response = get(client, '/events?' + query)
    assert response.status_code == 400
    assert response.json['error']['code'] == 'invalid_parameter'


def test_summary_zero_fill_and_half_open_range(client, store):
    clear_events(store)
    insert_event(store, timestamp=iso(NOW - timedelta(hours=24)))
    insert_event(store, timestamp=iso(NOW))
    result = get(client, '/events/summary').json
    assert len(result['series']) == 24
    assert sum(row['warning'] for row in result['series']) == 1
    assert result['by_sensor'] == [{'sensor': 'entry_monitor', 'count': 1}]
    assert get(client, '/events/summary?range=7d&bucket=day').status_code == 200
    assert get(client, '/events/summary?range=1d').status_code == 400
    assert get(client, '/events/summary?bucket=minute').status_code == 400


def test_empty_stats_and_histogram_boundaries(client, store):
    clear_events(store)
    empty = get(client, '/entry-monitor/stats').json
    assert empty['avg_confidence_confirmed'] is None
    assert all(row['count'] == 0 for row in empty['confidence_histogram'])
    for confidence in (0.0, 0.5, 0.6, 0.99, 1.0):
        insert_event(store, confidence=confidence)
    insert_event(store, status='motion_no_person', confidence=0.2)
    result = get(client, '/entry-monitor/stats').json
    assert result['persons_confirmed'] == 5 and result['motion_no_person'] == 1
    assert result['avg_confidence_confirmed'] == pytest.approx(0.618)
    assert [row['count'] for row in result['confidence_histogram']] == [1, 0, 0, 0, 0, 1, 1, 0, 0, 2]
    assert get(client, '/entry-monitor/stats?range=7d').status_code == 200


def test_card_create_patch_disable_and_duplicate(client):
    data = {'card_uid': ' abcdef12 ', 'label': ' New key ', 'notes': 'Test'}
    response = client.post('/api/v1/rfid/cards', headers=AUTH, json=data)
    assert response.status_code == 201
    original = response.json
    assert original['card_uid'] == 'ABCDEF12' and original['label'] == 'New key'
    assert client.post('/api/v1/rfid/cards', headers=AUTH, json=data).status_code == 409
    response = client.patch('/api/v1/rfid/cards/abcdef12', headers=AUTH, json={'active': False, 'notes': None})
    assert response.status_code == 200 and response.json['active'] is False
    assert response.json['label'] == 'New key'
    assert response.json['created_at'] == original['created_at']
    assert client.patch('/api/v1/rfid/cards/DEADBEEF', headers=AUTH, json={'active': False}).status_code == 404
    activity = get(client, '/rfid/activity?limit=7').json['events']
    assert len(activity) == 7 and all(e['sensor'] == 'rfid_auth' for e in activity)


@pytest.mark.parametrize('data', [None, [], {}, {'card_uid': 'XYZ', 'label': 'Test'}, {'card_uid': 'ABCDEF12', 'label': ' '}, {'card_uid': 'ABCDEF12', 'label': 'x'*41}, {'card_uid': 'ABCDEF12', 'label': 'Key', 'active': False}, {'card_uid': 'ABCDEF12', 'label': 'Key', 'notes': 3}])
def test_invalid_card_creation(client, data):
    response = client.post('/api/v1/rfid/cards', headers=AUTH, data=json.dumps(data), content_type='application/json')
    assert response.status_code == 400
    assert set(response.json) == {'error'}


@pytest.mark.parametrize('data', [{'active': 'false'}, {'active': 0}, {'card_uid': 'ABCDEF12'}, {'last_seen': 'bad'}, {}])
def test_invalid_patch(client, data):
    assert client.patch('/api/v1/rfid/cards/04A1B2C3', headers=AUTH, json=data).status_code == 400


def test_rfid_duplicate_creation_is_atomic(app):
    def create(_):
        return app.test_client().post('/api/v1/rfid/cards', headers=AUTH, json={'card_uid': 'ABCDEF12', 'label': 'Concurrent'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == [201, 409]


def test_write_security_and_error_shapes(client):
    url = '/api/v1/rfid/cards'
    assert client.post(url, headers={**AUTH, 'Origin': 'https://other.example'}, json={}).status_code == 403
    assert client.post(url, headers=AUTH, data='{}').status_code == 415
    assert client.post(url, headers=AUTH, data='{broken', content_type='application/json').status_code == 400
    assert client.post(url, headers=AUTH, json={'notes': 'x'*17000}).status_code == 413
    response = get(client, '/does-not-exist')
    assert response.status_code == 404 and response.json['error']['code'] == 'not_found'
    assert response.headers['Cache-Control'] == 'no-store'


def test_system_has_no_path_or_secrets(client, store):
    result = get(client, '/system')
    assert result.json['db']['events'] == 800
    assert result.json['db']['cards'] == 4
    assert result.json['mode'] == 'demo' and result.json['mqtt_connected'] is None
    assert result.json['db']['path_basename'] == 'test.db'
    assert str(store.path.parent) not in result.get_data(as_text=True)
    assert 'password' not in result.get_data(as_text=True).lower()


def test_health_database_failure_is_honest(client, store, tmp_path):
    store.path = tmp_path / 'missing.db'
    result = get(client, '/health')
    assert result.status_code == 503 and result.json['db_ok'] is False
    result = get(client, '/overview')
    assert result.status_code == 503 and result.json['error']['code'] == 'database_unavailable'
    assert not store.path.exists()


def test_seeding_is_repeatable_and_never_overwrites(tmp_path):
    from services.common import Store
    first = seed_demo_data(tmp_path / 'one.db', now=NOW)
    second = seed_demo_data(tmp_path / 'two.db', now=NOW)
    assert Store(first).rows('SELECT * FROM events') == Store(second).rows('SELECT * FROM events')
    before = hashlib.sha256(first.read_bytes()).digest()
    with pytest.raises(FileExistsError):
        seed_demo_data(first)
    assert hashlib.sha256(first.read_bytes()).digest() == before


def test_demo_refuses_committed_db_without_opening_it(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'database' / 'sentinelai.db'
    monkeypatch.setenv('SENTINELAI_DB_PATH', str(path))
    with pytest.raises(ValueError, match='committed hub database'):
        create_app()


def test_multiple_apps_do_not_share_database_or_auth(tmp_path, app):
    second = create_app(tmp_path / 'second.db', clock=lambda: NOW)
    clear_events(second.extensions['sentinel_providers'].store)
    assert get(second.test_client(), '/events').json['total_matching'] == 0
    assert get(app.test_client(), '/events').json['total_matching'] == 800


def test_demo_import_graph_has_no_hardware(tmp_path):
    # Fresh interpreter: old RFID tests legitimately import modules.* themselves.
    code = """
import sys
from dashboard_dev import create_app
app = create_app(sys.argv[1])
blocked = ('core.mqtt_client', 'core.module_loader', 'modules', 'gpiozero', 'picamera2', 'paho', 'ai_edge_litert')
assert not [name for name in sys.modules if any(name == p or name.startswith(p + '.') for p in blocked)]
assert app.test_client().get('/api/v1/health').status_code == 200
"""
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path / 'subprocess.db')], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_live_providers_are_unwired_adapters():
    from types import SimpleNamespace
    from dataclasses import make_dataclass
    Session = make_dataclass('Session', ['card_uid', 'card_label', 'expires_at'])
    session = Session('04A1B2C3', 'Dev', iso(NOW))
    provider = LiveAuthWindow(SimpleNamespace(current=lambda: session))
    assert provider.current()['active'] is True
    assert LiveAuthWindow(SimpleNamespace(current=lambda: None)).current() is None
    assert LiveConnectionStatus(NOW, lambda: True).current()['mqtt_connected'] is True


def test_event_source_tracks_ids_without_history_replay(app, store):
    source = app.extensions['sentinel_providers'].events
    last = source.latest_id()
    assert source.after(last) == []
    new_id = insert_event(store)
    assert [e['id'] for e in source.after(last)] == [new_id]
