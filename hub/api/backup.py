"""Authenticated, bounded downloads with cleanup on disconnect."""
import re
from threading import BoundedSemaphore
from flask import Blueprint, Response, current_app, request

from api.rate_limit import WriteLimiter
from services.backup import create_backup
from services.common import ServiceError

backup_bp = Blueprint('backup', __name__)


@backup_bp.record_once
def initialize(state):
    state.app.extensions['sentinel_backup_slot'] = BoundedSemaphore(1)
    state.app.extensions['sentinel_backup_limiter'] = WriteLimiter(limit=3)


@backup_bp.get('/backup')
def download_backup():
    from api.v1 import providers
    p = providers()
    current_app.extensions['sentinel_backup_limiter'].check(request.remote_addr or 'unknown')
    slot = current_app.extensions['sentinel_backup_slot']
    if not slot.acquire(blocking=False):
        raise ServiceError('backup_in_progress', 'A database backup is already being downloaded. Retry shortly.', 503)
    cleanup = file = None
    released = False

    def close():
        nonlocal released
        if released:
            return
        released = True
        try:
            if file:
                file.close()
        finally:
            try:
                if cleanup:
                    cleanup()
            finally:
                slot.release()

    try:
        path, cleanup = create_backup(p.store)
        file = path.open('rb')
        size = path.stat().st_size
        node = re.sub(r'[^A-Za-z0-9_-]', '_', p.node_id)[:40] or 'hub'
        filename = f'sentinelai-{node}-{p.clock():%Y%m%dT%H%M%SZ}.sqlite3'
        def chunks():
            try:
                while chunk := file.read(65536):
                    yield chunk
            finally:
                close()
        response = Response(chunks(), mimetype='application/vnd.sqlite3', headers={
            'Content-Disposition': f'attachment; filename="{filename}"', 'Content-Length': str(size)})
        response.call_on_close(close)
        return response
    except BaseException:
        close()
        raise
