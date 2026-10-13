"""Atomic card operations on the existing schema.

Unlike upsert_known_card, POST must never update an existing UID. PATCH only
updates requested fields, preserving timestamps concurrently touched by RFID.
"""
import re
import sqlite3
from services.common import ServiceError, iso


def uid(value):
    value = value.strip().upper() if isinstance(value, str) else ''
    if not re.fullmatch(r'[0-9A-F]{8,20}', value):
        raise ServiceError('invalid_uid', 'card_uid must contain 8 to 20 hexadecimal characters.')
    return value


def validate(data, create=False):
    if not isinstance(data, dict):
        raise ServiceError('invalid_body', 'A JSON object is required.')
    allowed = {'card_uid', 'label', 'notes'} if create else {'label', 'notes', 'active'}
    if not data or set(data) - allowed:
        raise ServiceError('invalid_body', 'Supply only supported card fields.')
    result = dict(data)
    if create:
        result['card_uid'] = uid(data.get('card_uid'))
    if create or 'label' in data:
        label = data.get('label')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 40:
            raise ServiceError('invalid_label', 'label must contain 1 to 40 non-whitespace characters.')
        result['label'] = label.strip()
    if 'notes' in data and data['notes'] is not None:
        if not isinstance(data['notes'], str) or len(data['notes']) > 2000:
            raise ServiceError('invalid_notes', 'notes must be null or a string of at most 2000 characters.')
    if 'active' in data and type(data['active']) is not bool:
        raise ServiceError('invalid_active', 'active must be a JSON boolean.')
    return result


def shape(row):
    return {**dict(row), 'active': bool(row['active'])}


def list_cards(providers):
    return [shape(row) for row in providers.store.rows('SELECT * FROM known_cards ORDER BY label, card_uid')]


def create_card(providers, data):
    value = validate(data, create=True)
    try:
        with providers.store.connection(write=True) as conn:
            conn.execute('INSERT INTO known_cards (card_uid, label, active, notes, created_at) VALUES (?, ?, 1, ?, ?)',
                         (value['card_uid'], value['label'], value.get('notes'), iso(providers.clock())))
            row = conn.execute('SELECT * FROM known_cards WHERE card_uid = ?', (value['card_uid'],)).fetchone()
    except sqlite3.IntegrityError:
        raise ServiceError('already_exists', 'A card with this UID already exists.', 409) from None
    return shape(row)


def patch_card(providers, card_uid, data):
    card_uid = uid(card_uid)
    value = validate(data)
    with providers.store.connection(write=True) as conn:
        # Field names come only from the allowlist in validate().
        result = conn.execute('UPDATE known_cards SET ' + ', '.join(f'{key} = ?' for key in value) + ' WHERE card_uid = ?', [*value.values(), card_uid])
        if result.rowcount == 0:
            raise ServiceError('not_found', 'Card not found.', 404)
        row = conn.execute('SELECT * FROM known_cards WHERE card_uid = ?', (card_uid,)).fetchone()
    return shape(row)
