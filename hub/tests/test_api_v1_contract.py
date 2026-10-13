"""Validate every Phase 1 route against the frontend-owned JSON Schema subset.

No new dependency: unsupported schema keywords fail instead of being ignored.
Phase 3 must reuse these fixtures in TypeScript runtime-guard tests.
"""
from datetime import datetime, timezone
import base64
import json
from pathlib import Path

from dashboard_dev import create_app

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'dashboard-ui/src/api/schema/responses.json').read_text(encoding='utf-8'))
AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'admin:dev').decode()}


def validate(value, schema):
    supported = {'$ref', 'anyOf', 'const', 'enum', 'type', 'properties', 'required', 'additionalProperties', 'items'}
    assert set(schema) <= supported, 'Unsupported schema keyword'
    if '$ref' in schema:
        return validate(value, SCHEMA['$defs'][schema['$ref'].split('/')[-1]])
    if 'anyOf' in schema:
        for branch in schema['anyOf']:
            try:
                validate(value, branch)
                return
            except AssertionError:
                pass
        raise AssertionError(f'No schema alternative matches {value!r}')
    if 'enum' in schema:
        assert value in schema['enum']
    if 'const' in schema:
        assert value == schema['const']
    kind = schema.get('type')
    if kind is None:
        return
    types = {'string': (str,), 'integer': (int,), 'number': (int, float), 'boolean': (bool,), 'object': (dict,), 'array': (list,), 'null': (type(None),)}
    assert type(value) in types[kind], (value, kind)
    if kind == 'object':
        assert set(schema['required']) <= set(value)
        if schema.get('additionalProperties') is False:
            assert set(value) <= set(schema['properties'])
        for key, item in value.items():
            validate(item, schema['properties'][key])
    elif kind == 'array':
        for item in value:
            validate(item, schema['items'])


def test_all_phase_one_contracts(tmp_path, monkeypatch):
    for key in ('SENTINELAI_DASHBOARD_USER', 'SENTINELAI_DASHBOARD_PASSWORD'):
        monkeypatch.delenv(key, raising=False)
    app = create_app(tmp_path / 'contracts.db', clock=lambda: datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
    client = app.test_client()
    paths = {'/health':'health', '/overview':'overview', '/devices':'devices', '/devices/hub':'deviceDetail',
             '/events':'events', '/events/summary':'summary', '/rfid/cards':'cards', '/rfid/activity':'activity',
             '/entry-monitor/stats':'entryStats', '/system':'system', '/insights':'insights'}
    for path, name in paths.items():
        response = client.get('/api/v1' + path, headers=AUTH)
        assert response.status_code == 200, path
        validate(response.json, SCHEMA['$defs'][name])
    created = client.post('/api/v1/rfid/cards', headers=AUTH, json={'card_uid':'ABCDEF12', 'label':'Contract card'})
    assert created.status_code == 201
    validate(created.json, SCHEMA['$defs']['card'])
    patched = client.patch('/api/v1/rfid/cards/ABCDEF12', headers=AUTH, json={'active':False})
    assert patched.status_code == 200
    validate(patched.json, SCHEMA['$defs']['card'])
    error = client.get('/api/v1/overview')
    assert error.status_code == 401
    validate(error.json, SCHEMA['$defs']['error'])


def test_validator_rejects_drift():
    import pytest
    with pytest.raises(AssertionError):
        validate({'devices': 'not a list'}, SCHEMA['$defs']['devices'])
    with pytest.raises(AssertionError):
        validate({'devices': [], 'unexpected': True}, SCHEMA['$defs']['devices'])
    with pytest.raises(AssertionError):
        validate(True, {'type': 'number'})
