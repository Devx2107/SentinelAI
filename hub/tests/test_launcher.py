"""Launcher validation must run before opening hardware or background workers."""
import sys
from unittest.mock import Mock

import pytest
import run


@pytest.fixture
def checked_env(monkeypatch, tmp_path):
    for key in tuple(run.os.environ):
        if key.startswith('SENTINELAI_'):
            monkeypatch.delenv(key)
    monkeypatch.setenv('SENTINELAI_DB_PATH', str(tmp_path/'live.db'))
    monkeypatch.setenv('SENTINELAI_DASHBOARD_USER', 'admin')
    monkeypatch.setenv('SENTINELAI_DASHBOARD_PASSWORD', 'test-secret')
    for name in ('MODEL_PATH', 'LABELS_PATH'):
        path = tmp_path/name
        path.write_text('fixture', encoding='utf-8')
        monkeypatch.setenv('SENTINELAI_' + name, str(path))
    monkeypatch.setattr(run.importlib.util, 'find_spec', lambda _: object())
    return tmp_path


def test_valid_configuration_passes_without_importing_hardware(checked_env):
    assert all(check['ok'] for check in run.preflight())


@pytest.mark.parametrize('name,value', [
    ('HTTP_PORT', 'bad'), ('HTTP_PORT', '0'), ('HTTP_PORT', '65536'),
    ('MQTT_PORT', '-1'), ('STALE_AFTER_SECONDS', '0'),
    ('CONFIDENCE_THRESHOLD', 'nan'), ('CONFIDENCE_THRESHOLD', '1.1'),
    ('RFID_AUTH_WINDOW_SECONDS', 'inf'), ('RFID_AUTH_WINDOW_SECONDS', '-1'),
    ('RFID_SPI_PORT', '-1'), ('RFID_RESET_PIN', '28'),
    ('HTTP_HOST', ''), ('MQTT_HOST', 'invalid host'), ('NODE_ID', 'bad/topic'),
    ('RFID_READER_FACTORY', 'no-colon'),
])
def test_preflight_reports_invalid_settings(checked_env, monkeypatch, name, value):
    monkeypatch.setenv('SENTINELAI_' + name, value)
    checks = {check['name']: check for check in run.preflight()}
    assert not checks[name.lower()]['ok']


def test_invalid_live_configuration_never_starts_hardware(checked_env, monkeypatch, capsys):
    import runtime
    start = Mock()
    monkeypatch.setattr(runtime, 'start_live', start)
    monkeypatch.setenv('SENTINELAI_HTTP_PORT', 'invalid')
    monkeypatch.setattr(sys, 'argv', ['run.py', '--mode', 'live', '--env-file', str(checked_env/'absent.env')])
    assert run.main() == 1
    start.assert_not_called()
    assert '"ready": false' in capsys.readouterr().out


def test_invalid_demo_port_never_creates_database(checked_env, monkeypatch):
    import dashboard_dev
    create = Mock()
    monkeypatch.setattr(dashboard_dev, 'create_app', create)
    monkeypatch.setenv('SENTINELAI_HTTP_PORT', '65536')
    monkeypatch.setattr(sys, 'argv', ['run.py', '--env-file', str(checked_env/'absent.env')])
    with pytest.raises(SystemExit) as error:
        run.main()
    assert error.value.code == 2
    create.assert_not_called()


@pytest.mark.parametrize('failure', ['signal', 'serve', 'generator'])
def test_demo_services_close_on_startup_failure(checked_env, monkeypatch, failure):
    import dashboard_dev
    from services import demo_generator
    app, generator, temporary = Mock(), Mock(), Mock()
    app.extensions = {'sentinel_providers': Mock(), 'demo_temp_directory': temporary}
    monkeypatch.setattr(dashboard_dev, 'create_app', lambda: app)
    monkeypatch.setattr(demo_generator, 'DemoGenerator', lambda _: generator)
    monkeypatch.setattr(sys, 'argv', ['run.py', '--env-file', str(checked_env/'absent.env')])
    signal = Mock()
    monkeypatch.setattr(run.signal, 'signal', signal)
    {'signal': signal, 'serve': app.run, 'generator': generator.start}[failure].side_effect = RuntimeError('startup failed')
    with pytest.raises(RuntimeError, match='startup failed'):
        run.main()
    generator.stop.assert_called_once()
    temporary.cleanup.assert_called_once()
