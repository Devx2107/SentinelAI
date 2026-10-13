"""Create a NEW demo database. Never overwrites or seeds an existing file."""
from datetime import timedelta
import argparse
import json
from pathlib import Path
import random
import sqlite3
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db import _SCHEMA
from services.common import iso, parse_time, utcnow


def seed_demo_data(path, *, now=None, seed=2107):
    now = now or utcnow()
    path = Path(path).resolve()
    protected = Path(__file__).resolve().parents[1] / 'database' / 'sentinelai.db'
    if path == protected.resolve():
        raise ValueError('The hub database is never a demo target.')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create rejects existing databases, including non-empty user data.
    with path.open('xb'):
        pass
    rng = random.Random(seed)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        devices = [
            ('hub', 'online', iso(now - timedelta(seconds=5)), ['pir', 'camera', 'entry_monitor', 'rfid']),
            ('node-zero-01', 'online', iso(now - timedelta(seconds=12)), ['pir']),
            ('node-zero-02', 'offline', iso(now - timedelta(hours=3)), ['pir']),
        ]
        conn.executemany('INSERT INTO devices VALUES (?, ?, ?, ?)', [(a, b, c, json.dumps(d)) for a, b, c, d in devices])
        cards = [('04A1B2C3', 'Dev', 1), ('04B2C3D4', 'Family', 1), ('04C3D4E5', 'Guest', 1), ('04D4E5F6', 'Retired key', 0)]
        conn.executemany('INSERT INTO known_cards VALUES (?, ?, ?, ?, ?, ?)',
                         [(uid, label, active, 'Synthetic demo card', iso(now - timedelta(days=7)), iso(now - timedelta(hours=i + 1))) for i, (uid, label, active) in enumerate(cards)])
        events = []
        for _ in range(800):
            # Weighted rejection sampling keeps morning/evening busiest.
            while True:
                stamp = now - timedelta(seconds=rng.randint(1, 7 * 86400))
                weight = 1 if stamp.hour in (*range(6, 10), *range(17, 23)) else 0.25
                if rng.random() <= weight:
                    break
            if rng.random() < 0.7:
                confirmed = rng.random() < 0.3
                sensor, status = 'entry_monitor', 'person_confirmed' if confirmed else 'motion_no_person'
                severity = 'warning' if confirmed else 'info'
                confidence = round(rng.uniform(0.55, 0.98) if confirmed else rng.uniform(0.05, 0.45), 3)
                node = 'hub'
                if confirmed and rng.random() < 0.05:
                    severity = 'critical'
            else:
                authorized = rng.random() < 0.85
                sensor, status = 'rfid_auth', 'card_authorized' if authorized else 'card_denied'
                severity, confidence, node = 'info' if authorized else 'warning', None, 'hub'
            events.append((iso(stamp), node, sensor, status, severity, confidence, f'DEMO: {status.replace("_", " ")} at front entry'))
        events.sort(key=lambda row: row[0])
        conn.executemany('INSERT INTO events (timestamp, node_id, sensor, status, severity, confidence, message) VALUES (?, ?, ?, ?, ?, ?, ?)', events)
        conn.commit()
    finally:
        conn.close()
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', help='New database filename (must not exist)')
    parser.add_argument('--as-of', help='Fixed ISO timestamp for reproducible fixtures')
    args = parser.parse_args()
    print(seed_demo_data(args.path, now=parse_time(args.as_of) if args.as_of else None))
