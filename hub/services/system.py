def system_status(providers):
    store = providers.store
    counts = store.rows('''SELECT (SELECT COUNT(*) FROM events) AS events,
        (SELECT COUNT(*) FROM devices) AS devices,
        (SELECT COUNT(*) FROM known_cards) AS cards''')[0]
    return {'node_id': providers.node_id, 'uptime_seconds': providers.uptime(),
            'db': {'path_basename': store.path.name, 'size_bytes': store.path.stat().st_size, **counts},
            'mqtt_connected': providers.connection.current()['mqtt_connected'],
            'stale_after_seconds': providers.stale_after_seconds, 'mode': providers.mode}
