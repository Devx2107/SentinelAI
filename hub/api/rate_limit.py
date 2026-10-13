"""Bounded per-process write limiter for the single-process hub."""
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from services.common import ServiceError


class WriteLimiter:
    def __init__(self, limit=30, window=60, clock=monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.clients, self.lock = OrderedDict(), Lock()

    def check(self, address):
        now = self.clock()
        with self.lock:
            # Expire inactive clients and bound storage without trusting forwarded IPs.
            for key in list(self.clients):
                if not self.clients[key] or now - self.clients[key][-1] >= self.window:
                    del self.clients[key]
            if address not in self.clients and len(self.clients) >= 1024:
                raise ServiceError('rate_limited', 'Write capacity reached. Retry in one minute.', 429)
            hits = self.clients.setdefault(address, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise ServiceError('rate_limited', 'Too many card writes. Retry in one minute.', 429)
            hits.append(now)
