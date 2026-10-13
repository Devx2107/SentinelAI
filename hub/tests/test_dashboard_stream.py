from datetime import datetime, timezone
from contextlib import contextmanager
import base64
import pytest
from dashboard_dev import create_app
from services.demo_generator import DemoGenerator
from api.rate_limit import WriteLimiter
from services.common import ServiceError

AUTH = {'Authorization': 'Basic ' + base64.b64encode(b'admin:dev').decode()}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv('SENTINELAI_DASHBOARD_USER', raising=False)
    monkeypatch.delenv('SENTINELAI_DASHBOARD_PASSWORD', raising=False)
    return create_app(tmp_path/'stream.db', clock=lambda: datetime(2026,10,13,12,tzinfo=timezone.utc))


def test_stream_tail_and_resume_and_close(app):
    p = app.extensions['sentinel_providers']
    response = app.test_client().get('/api/v1/stream', headers=AUTH, buffered=False)
    assert response.status_code == 200
    assert response.headers['X-Accel-Buffering'] == 'no'
    assert response.headers['Cache-Control'] == 'no-cache'
    iterator = iter(response.response)
    assert next(iterator).startswith(b'retry:')
    last = p.events.latest_id()
    DemoGenerator(p).tick()
    block = next(iterator)
    assert f'id: {last+1}'.encode() in block
    assert b'event: event' in block
    response.close()
    assert app.extensions['sentinel_stream_slots'].active == 0
    resumed = app.test_client().get('/api/v1/stream', headers={**AUTH,'Last-Event-ID':str(last)}, buffered=False)
    it = iter(resumed.response)
    next(it)
    assert f'id: {last+1}'.encode() in next(it)
    resumed.close()


def test_stream_cap_and_invalid_cursor(app):
    responses=[]
    try:
        for _ in range(10):
            responses.append(app.test_client().get('/api/v1/stream', headers=AUTH, buffered=False))
        assert app.test_client().get('/api/v1/stream', headers=AUTH).status_code == 503
        assert app.test_client().get('/api/v1/stream', headers={**AUTH,'Last-Event-ID':'bad'}).status_code == 400
    finally:
        for r in responses: r.close()
    assert app.extensions['sentinel_stream_slots'].active == 0


def test_stream_does_not_hold_connection_between_chunks(app,monkeypatch):
    p=app.extensions['sentinel_providers']
    original=p.store.connection
    active=0
    @contextmanager
    def tracked(*args,**kwargs):
        nonlocal active
        with original(*args,**kwargs) as connection:
            active+=1
            try: yield connection
            finally: active-=1
    monkeypatch.setattr(p.store,'connection',tracked)
    response=app.test_client().get('/api/v1/stream',headers={**AUTH,'Last-Event-ID':'799'},buffered=False)
    it=iter(response.response)
    for _ in range(5):
        next(it)
        assert active==0
    response.close()


def test_demo_lifecycle_and_live_guard(app):
    p=app.extensions['sentinel_providers']
    generator=DemoGenerator(p,interval=100)
    generator.start()
    assert generator.thread.is_alive()
    generator.stop()
    assert not generator.thread.is_alive()
    for _ in range(11): generator.tick()
    assert p.auth.current()['active']
    p.mode='live'
    with pytest.raises(ValueError): DemoGenerator(p)


def test_rate_limit_expires_without_sleeping():
    now=[0]
    limiter=WriteLimiter(limit=2,window=60,clock=lambda:now[0])
    limiter.check('one');limiter.check('one');limiter.check('two')
    with pytest.raises(ServiceError) as caught:limiter.check('one')
    assert caught.value.status==429
    now[0]=60
    limiter.check('one')


def test_ui_shell_fallback_and_assets(app):
    client=app.test_client()
    shell=client.get('/app/')
    assert shell.status_code==200
    assert b'SentinelAI' in shell.data
    assert client.get('/app/devices/hub').data==shell.data
    assert client.get('/app/assets/missing.js').status_code==404
    assert "frame-ancestors 'none'" in shell.headers['Content-Security-Policy']
    assert client.get('/api/v1/readiness',headers=AUTH).json['checks'][1]['ok'] is False
