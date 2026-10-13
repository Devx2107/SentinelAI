"""Bounded resumable streams; each database read opens and closes its connection."""
import json
from threading import Lock, Event
from time import monotonic
from flask import Blueprint, Response, current_app, request
from services.common import ServiceError, integer
from services.devices import list_devices

stream_bp = Blueprint('stream', __name__)


class StreamSlots:
    def __init__(self, maximum=10):
        self.maximum, self.active, self.lock = maximum, 0, Lock()

    def acquire(self):
        with self.lock:
            if self.active >= self.maximum:
                raise ServiceError('too_many_streams', 'All live stream slots are occupied. Retry shortly.', 503)
            self.active += 1
        released = False

        def release():
            nonlocal released
            with self.lock:
                if not released:
                    self.active -= 1
                    released = True
        return release


def packet(kind, data, event_id=None):
    prefix = f'id: {event_id}\n' if event_id is not None else ''
    return prefix + f'event: {kind}\ndata: {json.dumps(data, separators=(",", ":"))}\n\n'


@stream_bp.get('/stream')
def stream():
    from api.v1 import providers
    p = providers()
    last = request.headers.get('Last-Event-ID')
    # Capture before the first yield: inserts during connection setup are not lost.
    cursor = p.events.latest_id() if last is None else integer(last, 'Last-Event-ID', minimum=0, maximum=9223372036854775807)
    slots = current_app.extensions['sentinel_stream_slots']
    release = slots.acquire()
    stop = Event()

    def generate():
        nonlocal cursor
        seen, previous_auth = {}, object()
        device_tick = ping_tick = 0.0
        try:
            yield 'retry: 3000\n\n'
            while not stop.is_set():
                rows = p.events.after(cursor)
                for row in rows:
                    cursor = row['id']
                    yield packet('event', row, cursor)
                tick = monotonic()
                if tick - device_tick >= 5:
                    for device in list_devices(p):
                        signature = (device['effective_status'], device['last_seen'])
                        if seen.get(device['node_id']) != signature:
                            seen[device['node_id']] = signature
                            yield packet('device', device)
                    device_tick = tick
                auth = p.auth.current()
                if auth != previous_auth:
                    previous_auth = auth
                    yield packet('auth_window', auth)
                if tick - ping_tick >= 15:
                    yield packet('ping', {})
                    ping_tick = tick
                # Drain a backlog without delaying every batch; never hold a DB handle here.
                if len(rows) < 200:
                    stop.wait(1)
        finally:
            release()

    response = Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    response.call_on_close(lambda: (stop.set(), release()))
    return response
