"""UTC rolling-window aggregation with zero-filled calendar buckets."""
from datetime import timedelta
from services.common import ServiceError, iso, range_start


def bounds(range_value, now, bucket):
    start = range_start(range_value, now)
    if bucket not in ('hour', 'day'):
        raise ServiceError('invalid_parameter', 'bucket must be hour or day.')
    floor = lambda value: value.replace(minute=0, second=0, microsecond=0, **({'hour': 0} if bucket == 'day' else {}))
    step = timedelta(hours=1) if bucket == 'hour' else timedelta(days=1)
    points, cursor = [], floor(start)
    while cursor < now:
        points.append(iso(cursor).replace('.000000', ''))
        cursor += step
    return start, points


def series(providers, range_value, bucket, column, keys, sensor=None):
    now = providers.clock()
    start, points = bounds(range_value, now, bucket)
    # column is internal and not supplied by HTTP callers.
    if column not in ('severity', 'status'):
        raise ValueError('Unsupported aggregation column')
    fmt = '%Y-%m-%dT%H:00:00Z' if bucket == 'hour' else '%Y-%m-%dT00:00:00Z'
    where = 'julianday(timestamp) >= julianday(?) AND julianday(timestamp) < julianday(?)'
    params = [iso(start), iso(now)]
    if sensor:
        where += ' AND sensor = ?'
        params.append(sensor)
    rows = providers.store.rows(f'SELECT strftime(?, timestamp) AS t, {column} AS kind, COUNT(*) AS n FROM events WHERE {where} GROUP BY t, {column}', [fmt, *params])
    result = {point: {'t': point, **dict.fromkeys(keys, 0)} for point in points}
    for row in rows:
        if row['t'] in result and row['kind'] in keys:
            result[row['t']][row['kind']] = row['n']
    return list(result.values()), where, params


def event_summary(providers, range_value='24h', bucket='hour'):
    values, where, params = series(providers, range_value, bucket, 'severity', ('info', 'warning', 'critical'))
    sensors = providers.store.rows(f'SELECT sensor, COUNT(*) AS count FROM events WHERE {where} GROUP BY sensor ORDER BY count DESC, sensor', params)
    return {'range': range_value, 'bucket': bucket, 'series': values, 'by_sensor': sensors}


def entry_stats(providers, range_value='24h'):
    bucket = 'hour' if range_value == '24h' else 'day'
    values, where, params = series(providers, range_value, bucket, 'status', ('person_confirmed', 'motion_no_person'), 'entry_monitor')
    aggregate = providers.store.rows(f'''SELECT
        COALESCE(SUM(status = 'person_confirmed'), 0) AS persons_confirmed,
        COALESCE(SUM(status = 'motion_no_person'), 0) AS motion_no_person,
        AVG(CASE WHEN status = 'person_confirmed' THEN confidence END) AS avg_confidence_confirmed
        FROM events WHERE {where}''', params)[0]
    histogram = [{'bucket': f'{i / 10:.1f}-{(i + 1) / 10:.1f}', 'count': 0} for i in range(10)]
    rows = providers.store.rows(f'''SELECT MIN(CAST(confidence * 10 AS INTEGER), 9) AS bin, COUNT(*) AS count
        FROM events WHERE {where} AND status = 'person_confirmed' AND confidence BETWEEN 0 AND 1 GROUP BY bin''', params)
    for row in rows:
        histogram[row['bin']]['count'] = row['count']
    return {'range': range_value, **aggregate, 'confidence_histogram': histogram, 'series': values}
