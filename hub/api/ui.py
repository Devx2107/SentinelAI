from pathlib import Path
from flask import Blueprint, redirect, send_from_directory

ui_bp = Blueprint('dashboard_ui', __name__)
BUILD = Path(__file__).resolve().parents[1] / 'static' / 'dashboard'


@ui_bp.get('/')
def root():
    return redirect('/app/')


@ui_bp.get('/app/', defaults={'path': ''})
@ui_bp.get('/app/<path:path>')
def shell(path):
    if path.startswith('assets/'):
        return send_from_directory(BUILD, path, max_age=31536000)
    response = send_from_directory(BUILD, 'index.html', max_age=0)
    response.headers['Cache-Control'] = 'no-cache'
    return response


@ui_bp.after_request
def headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response
