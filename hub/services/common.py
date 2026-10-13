"""Shared parsing, clock and database helpers."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class ServiceError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def parse_time(value, name='timestamp'):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise ServiceError('invalid_parameter', f'{name} must be an ISO-8601 timestamp with timezone.') from None


def integer(value, name, minimum=1, maximum=200):
    try:
        result = int(str(value))
        if not minimum <= result <= maximum:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ServiceError('invalid_parameter', f'{name} must be an integer from {minimum} to {maximum}.') from None


class Store:
    """Per-app DB path. Connections never outlive a query/transaction.

    Opening mode=rw prevents a mistyped live path creating an empty database.
    This avoids changing the hub's process-global config during demo/tests.
    """
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connection(self, write=False):
        conn = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            if write:
                conn.execute('BEGIN IMMEDIATE')
            else:
                conn.execute('PRAGMA query_only = ON')
            yield conn
            if write:
                conn.commit()
        except BaseException:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def rows(self, sql, params=()):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]


def range_start(value, now):
    from datetime import timedelta
    if value not in ('24h', '7d'):
        raise ServiceError('invalid_parameter', 'range must be 24h or 7d.')
    return now - timedelta(hours=24 if value == '24h' else 168)
