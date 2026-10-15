"""One synthetic producer per demo app, never per subscriber."""
from datetime import timedelta
from threading import Event, Thread
import logging
import random
from services.common import iso


class DemoGenerator:
    def __init__(self, providers, interval=4):
        if providers.mode != 'demo':
            raise ValueError('Synthetic events are prohibited in live mode')
        self.p, self.interval = providers, interval
        self.stop_event = Event()
        self.thread = None
        self.rng = random.Random(2107)
        self.step = 0

    def tick(self):
        now = self.p.clock()
        self.step += 1
        authorized = self.step % 11 == 0
        person = self.rng.random() < 0.3
        status = 'card_authorized' if authorized else ('person_confirmed' if person else 'motion_no_person')
        with self.p.store.connection(write=True) as conn:
            conn.execute("UPDATE devices SET last_seen = ? WHERE status = 'online'", (iso(now),))
            conn.execute('INSERT INTO events (timestamp,node_id,sensor,status,severity,confidence,message) VALUES (?,?,?,?,?,?,?)',
                (iso(now), 'hub', 'rfid_auth' if authorized else 'entry_monitor', status, 'warning' if person and not authorized else 'info', None if authorized else round(self.rng.uniform(.6,.97) if person else self.rng.uniform(.08,.35), 3), 'DEMO: ' + status.replace('_', ' ') + ' at front entry'))
        if authorized:
            self.p.auth.set(dict(card_uid='04A1B2C3', card_label='Dev', expires_at=iso(now + timedelta(seconds=30))))

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def run():
            while not self.stop_event.wait(self.interval):
                try:
                    self.tick()
                except Exception:
                    logging.getLogger(__name__).exception('Demo generation failed')
        self.thread = Thread(target=run, name='sentinel-demo', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.ident is not None:
            self.thread.join(timeout=6)
