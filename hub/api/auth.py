"""Basic auth for v2, independent of v1 private helpers."""
import hmac
import os
from flask import current_app, request
from services.common import ServiceError


def require_auth():
    # Overrides are supplied only by the standalone demo app factory.
    user = current_app.config.get('DASHBOARD_USER', os.getenv('SENTINELAI_DASHBOARD_USER'))
    password = current_app.config.get('DASHBOARD_PASSWORD', os.getenv('SENTINELAI_DASHBOARD_PASSWORD'))
    if not user or not password:
        raise ServiceError('auth_not_configured', 'Dashboard credentials are not configured.', 500)
    auth = request.authorization
    valid_user = hmac.compare_digest((auth.username or '').encode(), user.encode()) if auth else False
    valid_password = hmac.compare_digest((auth.password or '').encode(), password.encode()) if auth else False
    if not auth or auth.type.lower() != 'basic' or not (valid_user & valid_password):
        raise ServiceError('unauthorized', 'Valid dashboard credentials are required.', 401)
    if request.method in ('POST', 'PATCH'):
        # Basic auth is ambient browser authority. Reject cross-origin writes.
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
            raise ServiceError('forbidden_origin', 'Cross-origin writes are not allowed.', 403)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise ServiceError('forbidden_origin', 'Cross-site writes are not allowed.', 403)
        if not request.is_json:
            raise ServiceError('invalid_body', 'Content-Type must be application/json.', 415)
        if request.content_length is not None and request.content_length > 16384:
            raise ServiceError('request_too_large', 'Card requests are limited to 16 KiB.', 413)
