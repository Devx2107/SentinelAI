"""Read-only security triage derived from recorded events and device status."""
from datetime import timedelta
from urllib.parse import urlencode, quote

from services.common import iso
from services.devices import list_devices


def security_insights(providers):
    now = providers.clock()
    hour = iso(now - timedelta(hours=1))
    day = iso(now - timedelta(hours=24))
    previous = iso(now - timedelta(hours=48))
    end = iso(now)
    store = providers.store
    # All counters share one database snapshot, including the previous-day comparison.
    with store.connection() as connection:
        connection.execute('BEGIN')
        counts = dict(connection.execute('''SELECT
            COALESCE(SUM(julianday(timestamp) >= julianday(?)), 0) AS events_24h,
            COALESCE(SUM(julianday(timestamp) < julianday(?)), 0) AS events_previous_24h,
            COALESCE(SUM(julianday(timestamp) >= julianday(?) AND severity = 'warning'), 0) AS warnings_1h,
            COALESCE(SUM(julianday(timestamp) >= julianday(?) AND severity = 'critical'), 0) AS critical_1h,
            COALESCE(SUM(julianday(timestamp) >= julianday(?) AND sensor = 'rfid_auth' AND status = 'card_denied'), 0) AS cards_denied_1h
            FROM events WHERE julianday(timestamp) >= julianday(?) AND julianday(timestamp) < julianday(?)''',
            (day, day, hour, hour, hour, previous, end)).fetchone())
        top_devices = [dict(row) for row in connection.execute('''SELECT node_id, COUNT(*) AS events,
            COALESCE(SUM(severity IN ('warning', 'critical')), 0) AS attention_events
            FROM events WHERE julianday(timestamp) >= julianday(?) AND julianday(timestamp) < julianday(?)
            GROUP BY node_id ORDER BY events DESC, node_id LIMIT 5''', (day, end))]
    current, old = counts['events_24h'], counts['events_previous_24h']
    comparison = {'current': current, 'previous': old, 'difference': current - old,
                  'percent_change': round((current - old) / old * 100, 1) if old else None}
    alerts = []
    for severity, key in (('critical', 'critical_1h'), ('warning', 'warnings_1h')):
        count = counts[key]
        if count:
            alerts.append(dict(id=f'recent-{severity}', severity=severity,
                title=f'{count} {severity} event' + ('s' if count != 1 else '') + ' in the last hour',
                detail='Open the timeline to review the recorded activity and its context.',
                href='/events?' + urlencode({'severity': severity, 'since': hour})))
    if counts['cards_denied_1h']:
        alerts.append(dict(id='access-denied', severity='warning', title='Recent access attempts were denied',
            detail=f"{counts['cards_denied_1h']} denied card scans in the last hour.",
            href='/events?' + urlencode({'sensor': 'rfid_auth', 'status': 'card_denied', 'since': hour})))
    for device in list_devices(providers):
        if device['effective_status'] in ('offline', 'stale'):
            alerts.append(dict(id='device-' + device['node_id'], severity='warning',
                title=f"{device['node_id']} is {device['effective_status']}",
                detail='Check its power and network connection. Status comes from the latest recorded heartbeat.',
                href='/devices/' + quote(device['node_id'], safe='')))
    if providers.mode == 'live' and providers.connection.current()['mqtt_connected'] is False:
        alerts.append(dict(id='mqtt-disconnected', severity='critical', title='MQTT broker is disconnected',
            detail='New node messages may not reach the hub until the connection recovers.', href='/system'))
    return {'generated_at': end, 'recent': {key: counts[key] for key in ('warnings_1h', 'critical_1h', 'cards_denied_1h')},
            'comparison': comparison, 'alerts': alerts, 'top_devices': top_devices}
