import json
from services.common import ServiceError, parse_time


def shape_device(row, now, stale_after):
    result = dict(row)
    try:
        age = max(0.0, (now - parse_time(row['last_seen'])).total_seconds()) if row['last_seen'] else None
    except ServiceError:
        age = None
    result['seconds_since_seen'] = age
    status = row['status']
    if status == 'online' and (age is None or age > stale_after):
        status = 'stale'
    result['effective_status'] = status if status in ('online', 'stale', 'offline') else 'offline'
    try:
        capabilities = json.loads(row['capabilities'] or '[]')
        result['capabilities'] = capabilities if isinstance(capabilities, list) else []
    except (ValueError, TypeError):
        result['capabilities'] = []
    return result


def list_devices(providers):
    now = providers.clock()
    return [shape_device(row, now, providers.stale_after_seconds) for row in providers.store.rows('SELECT * FROM devices ORDER BY node_id')]


def get_device(providers, node_id):
    rows = providers.store.rows('SELECT * FROM devices WHERE node_id = ?', (node_id,))
    if not rows:
        raise ServiceError('not_found', 'Device not found.', 404)
    result = shape_device(rows[0], providers.clock(), providers.stale_after_seconds)
    result['recent_events'] = providers.store.rows('SELECT * FROM events WHERE node_id = ? ORDER BY id DESC LIMIT 20', (node_id,))
    return result
