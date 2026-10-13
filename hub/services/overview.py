from datetime import timedelta
from services.common import iso
from services.devices import list_devices


def overview(providers):
    now = providers.clock()
    devices = list_devices(providers)
    counts = {'devices_total': len(devices)}
    counts.update({f'devices_{status}': sum(d['effective_status'] == status for d in devices) for status in ('online', 'stale', 'offline')})
    counts.update(providers.store.rows('''SELECT COUNT(*) AS events_24h,
        COALESCE(SUM(severity = 'warning'), 0) AS warnings_24h,
        COALESCE(SUM(severity = 'critical'), 0) AS critical_24h,
        COALESCE(SUM(sensor = 'entry_monitor' AND status = 'person_confirmed'), 0) AS persons_confirmed_24h,
        COALESCE(SUM(sensor = 'rfid_auth' AND status = 'card_denied'), 0) AS cards_denied_24h
        FROM events WHERE julianday(timestamp) >= julianday(?) AND julianday(timestamp) < julianday(?)''', (iso(now - timedelta(hours=24)), iso(now)))[0])
    return {'hub': {'node_id': providers.node_id, 'uptime_seconds': providers.uptime()},
            'counts': counts, 'auth_window': providers.auth.current(),
            'latest_events': providers.store.rows('SELECT * FROM events ORDER BY id DESC LIMIT 10')}
