"""Hardware-free regression coverage for MQTT and hub lifecycle failures."""

from unittest.mock import Mock, call

import pytest

from core import module_loader
from core.mqtt_client import MQTTClient
from shared.mqtt_topics import status_topic
from config import config


@pytest.fixture
def mqtt_client(monkeypatch):
    transport = Mock()
    transport.is_connected.return_value = False
    transport.publish.return_value.rc = 0
    monkeypatch.setattr("core.mqtt_client.mqtt.Client", Mock(return_value=transport))
    return MQTTClient(), transport


def test_subscriptions_survive_initial_connection_and_reconnect(mqtt_client):
    client, transport = mqtt_client
    callback = Mock()
    client.subscribe("sentinelai/+/status", callback)
    transport.subscribe.assert_not_called()
    for _ in range(2):
        client._on_connect(transport, None, {}, 0)
    assert transport.subscribe.call_args_list == [call("sentinelai/+/status")] * 2
    handler = transport.message_callback_add.call_args.args[1]
    handler(transport, None, Mock(topic="sentinelai/edge/status", payload=b"online"))
    callback.assert_called_once_with("sentinelai/edge/status", "online")


def test_live_subscription_and_rejected_connection(mqtt_client):
    client, transport = mqtt_client
    transport.is_connected.return_value = True
    client.subscribe("sentinelai/+/status", Mock())
    transport.subscribe.assert_called_once()
    transport.reset_mock()
    client._on_connect(transport, None, {}, 5)
    transport.subscribe.assert_not_called()
    transport.publish.assert_not_called()


def test_clean_disconnect_waits_before_stopping_network_loop(mqtt_client):
    client, transport = mqtt_client
    transport.reset_mock()
    transport.is_connected.return_value = True
    client.disconnect()
    assert transport.mock_calls == [
        call.is_connected(),
        call.publish(status_topic(config.node.node_id), "offline", qos=1, retain=True),
        call.publish().wait_for_publish(timeout=5),
        call.disconnect(),
        call.loop_stop(),
    ]


def test_disconnect_cleans_up_even_if_publish_fails(mqtt_client):
    client, transport = mqtt_client
    transport.is_connected.return_value = True
    transport.publish.side_effect = RuntimeError("network failed")
    with pytest.raises(RuntimeError):
        client.disconnect()
    transport.disconnect.assert_called_once()
    transport.loop_stop.assert_called_once()


def test_failed_module_start_rolls_back_in_reverse_order(monkeypatch):
    first, failing, untouched = [Mock(module_id=name) for name in ("first", "fail", "last")]
    failing.start.side_effect = RuntimeError("camera unavailable")
    calls = Mock()
    calls.attach_mock(first, "first")
    calls.attach_mock(failing, "failing")
    monkeypatch.setattr(module_loader, "build_modules", lambda *args: [first, failing, untouched])
    loader = module_loader.ModuleLoader(Mock())
    with pytest.raises(RuntimeError, match="camera unavailable"):
        loader.start_all()
    assert calls.mock_calls == [call.first.start(), call.failing.start(), call.failing.stop(), call.first.stop()]
    untouched.start.assert_not_called()
    untouched.stop.assert_called_once()  # Constructors may already own hardware.
    loader.stop_all()
    first.stop.assert_called_once()


def test_module_cleanup_continues_after_stop_error(monkeypatch):
    first, second = Mock(module_id="first"), Mock(module_id="second")
    second.stop.side_effect = RuntimeError("cleanup failed")
    monkeypatch.setattr(module_loader, "build_modules", lambda *args: [first, second])
    loader = module_loader.ModuleLoader(Mock())
    loader.start_all()
    loader.start_all()
    loader.stop_all()
    first.start.assert_called_once()
    first.stop.assert_called_once()


def test_health_without_hardware():
    from app import app

    response = app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "node_id": config.node.node_id}


def test_hub_startup_failure_disconnects_mqtt(monkeypatch):
    import app

    transport = Mock()
    loader = Mock()
    loader.start_all.side_effect = RuntimeError("startup failed")
    monkeypatch.setattr(app, "init_db", Mock())
    monkeypatch.setattr(app, "DeviceRegistry", Mock())
    monkeypatch.setattr(app, "get_mqtt_client", lambda: transport)
    monkeypatch.setattr(app, "ModuleLoader", Mock(return_value=loader))
    monkeypatch.setattr(app.signal, "signal", Mock())
    monkeypatch.setattr(app, "_module_loader", None)
    with pytest.raises(RuntimeError, match="startup failed"):
        app.main()
    loader.stop_all.assert_called_once()
    transport.disconnect.assert_called_once()
