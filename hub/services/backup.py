"""Consistent disk-backed SQLite snapshots without blocking writers for a copy."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic

from services.common import ServiceError


def create_backup(store, *, timeout_seconds=15):
    directory = TemporaryDirectory(prefix='sentinel-backup-')
    path = Path(directory.name) / 'snapshot.sqlite3'
    deadline = monotonic() + timeout_seconds

    def progress(_status, _remaining, _total):
        if monotonic() > deadline:
            raise ServiceError('backup_timeout', 'The database is busy. Please retry the backup.', 503)

    try:
        with store.connection() as source:
            destination = sqlite3.connect(path)
            try:
                source.backup(destination, pages=128, progress=progress, sleep=.01)
                if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ServiceError('backup_failed', 'The snapshot failed its integrity check.', 503)
            finally:
                destination.close()
        return path, directory.cleanup
    except BaseException:
        directory.cleanup()
        raise
