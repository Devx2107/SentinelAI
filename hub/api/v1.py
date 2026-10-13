"""Dashboard v2 REST routes. Hardware/live providers are never imported here."""
import sqlite3
from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from api.auth import require_auth
from services.common import ServiceError
from services.devices import get_device, list_devices
from services.events import list_events
from services.overview import overview
from services.rfid import create_card, list_cards, patch_card
from services.stats import entry_stats, event_summary
from services.system import system_status
from services.insights import security_insights

api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')
from api.stream import stream_bp, StreamSlots
api_v1.register_blueprint(stream_bp)
from api.backup import backup_bp
api_v1.register_blueprint(backup_bp)


@api_v1.record_once
def initialize(state):
    state.app.extensions['sentinel_stream_slots'] = StreamSlots()
    from api.rate_limit import WriteLimiter
    state.app.extensions['sentinel_write_limiter'] = WriteLimiter()


def providers():
    value = current_app.extensions.get('sentinel_providers')
    if value is None:
        raise ServiceError('providers_unavailable', 'Dashboard providers are not configured; use the demo runner until live integration.', 503)
    return value


@api_v1.before_request
def authenticate():
    if request.endpoint != 'api_v1.health':
        require_auth()
    if request.method in ('POST', 'PATCH') and request.path.startswith('/api/v1/rfid/'):
        current_app.extensions['sentinel_write_limiter'].check(request.remote_addr or 'unknown')


@api_v1.after_request
def response_headers(response):
    if response.mimetype != 'text/event-stream':
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@api_v1.errorhandler(ServiceError)
def service_error(error):
    response = jsonify(error={'code': error.code, 'message': error.message})
    response.status_code = error.status
    if error.status == 401:
        response.headers['WWW-Authenticate'] = 'Basic realm="SentinelAI Dashboard", charset="UTF-8"'
    if error.status == 429:
        response.headers['Retry-After'] = '60'
    return response


@api_v1.errorhandler(sqlite3.Error)
def database_error(error):
    current_app.logger.warning('Dashboard database unavailable: %s', type(error).__name__)
    return service_error(ServiceError('database_unavailable', 'Dashboard database is unavailable.', 503))


@api_v1.errorhandler(HTTPException)
def http_error(error):
    return service_error(ServiceError('invalid_request', error.name, error.code))


@api_v1.errorhandler(Exception)
def internal_error(error):
    current_app.logger.exception('Dashboard request failed')
    return service_error(ServiceError('internal_error', 'The request could not be completed. Please retry.', 500))


@api_v1.get('/health')
def health():
    p = providers()
    try:
        p.store.rows('SELECT id FROM events LIMIT 1')
        db_ok = True
    except sqlite3.Error:
        db_ok = False
    return jsonify(status='ok' if db_ok else 'degraded', node_id=p.node_id,
                   uptime_seconds=p.uptime(), db_ok=db_ok, version='dashboard-v2'), 200 if db_ok else 503


@api_v1.get('/overview')
def get_overview():
    return jsonify(overview(providers()))


@api_v1.get('/insights')
def insights():
    return jsonify(security_insights(providers()))


@api_v1.get('/devices')
def devices():
    return jsonify(devices=list_devices(providers()))


@api_v1.get('/devices/<node_id>')
def device(node_id):
    return jsonify(get_device(providers(), node_id))


@api_v1.get('/events')
def events():
    return jsonify(list_events(providers(), request.args))


@api_v1.get('/events/summary')
def summary():
    return jsonify(event_summary(providers(), request.args.get('range', '24h'), request.args.get('bucket', 'hour')))


@api_v1.get('/rfid/cards')
def cards():
    return jsonify(cards=list_cards(providers()))


def body():
    # Limit actual reads too, including requests without Content-Length.
    raw = request.stream.read(16385)
    if len(raw) > 16384:
        raise ServiceError('request_too_large', 'Card requests are limited to 16 KiB.', 413)
    try:
        return current_app.json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ServiceError('invalid_body', 'Request must contain valid JSON.', 400) from None


@api_v1.post('/rfid/cards')
def add_card():
    return jsonify(create_card(providers(), body())), 201


@api_v1.patch('/rfid/cards/<card_uid>')
def edit_card(card_uid):
    return jsonify(patch_card(providers(), card_uid, body()))


@api_v1.get('/rfid/activity')
def activity():
    return jsonify(events=list_events(providers(), {'sensor': 'rfid_auth', 'limit': request.args.get('limit', 50)})['events'])


@api_v1.get('/entry-monitor/stats')
def entry():
    return jsonify(entry_stats(providers(), request.args.get('range', '24h')))


@api_v1.get('/system')
def system():
    return jsonify(system_status(providers()))


@api_v1.get('/readiness')
def readiness():
    p = providers()
    if p.mode == 'demo':
        checks = [dict(name='Dashboard & API', ok=True, detail='Demo environment; synthetic events are enabled by the runner.'),
                  dict(name='Raspberry Pi hardware', ok=False, detail='Not connected in demo mode.'),
                  dict(name='RFID reader', ok=False, detail='Configure a physical reader adapter on the Pi.')]
    else:
        checks = current_app.extensions.get('sentinel_readiness', []) + [dict(name='MQTT broker', ok=bool(p.connection.current()['mqtt_connected']), detail='Current broker connection state.')]
        reader = current_app.extensions.get('sentinel_reader')
        if reader is not None and hasattr(reader, 'ready'):
            checks = [{**c, 'ok': reader.ready, 'detail': 'Reader polling is active.' if reader.ready else 'Reader polling failed; check the hub logs and wiring.'} if c['name'] == 'RFID reader' else c for c in checks]
    return jsonify(checks=checks)


@api_v1.route('/<path:unknown>', methods=['GET', 'POST', 'PATCH', 'DELETE', 'PUT'])
def unknown_route(unknown):
    raise ServiceError('not_found', 'API endpoint not found.', 404)
