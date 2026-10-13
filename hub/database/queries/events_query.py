"""Bounded keyset pagination with bound values for every user filter."""
from services.common import ServiceError, integer, iso, parse_time


def filters(args):
    clauses, params = [], []
    for key in ('sensor', 'node_id'):
        if args.get(key):
            clauses.append(f'{key} = ?')
            params.append(args[key])
    for key in ('severity', 'status'):
        if args.get(key):
            values = [v.strip() for v in args[key].split(',') if v.strip()]
            if not values or len(values) > 20:
                raise ServiceError('invalid_parameter', f'{key} requires 1 to 20 values.')
            clauses.append(f"{key} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    dates = {}
    for key, operator in (('since', '>='), ('until', '<')):
        if args.get(key):
            dates[key] = parse_time(args[key], key)
            clauses.append(f'julianday(timestamp) {operator} julianday(?)')
            params.append(iso(dates[key]))
    if len(dates) == 2 and dates['since'] >= dates['until']:
        raise ServiceError('invalid_parameter', 'since must be before until.')
    if args.get('q'):
        if len(args['q']) > 500:
            raise ServiceError('invalid_parameter', 'q must be at most 500 characters.')
        # instr treats percent and underscore as literal substring characters.
        clauses.append('instr(lower(message), lower(?)) > 0')
        params.append(args['q'])
    return clauses, params


def query_events(store, args):
    limit = integer(args.get('limit', 50), 'limit')
    clauses, params = filters(args)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    # Count and page share a read snapshot, even if a producer inserts concurrently.
    with store.connection() as conn:
        conn.execute('BEGIN')
        total = conn.execute('SELECT COUNT(*) FROM events' + where, params).fetchone()[0]
        if args.get('cursor') is not None:
            clauses.append('id < ?')
            params.append(integer(args['cursor'], 'cursor', maximum=9223372036854775807))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        rows = [dict(row) for row in conn.execute('SELECT * FROM events' + where + ' ORDER BY id DESC LIMIT ?', [*params, limit + 1])]
    page = rows[:limit]
    return {'events': page, 'next_cursor': page[-1]['id'] if len(rows) > limit else None, 'total_matching': total}
