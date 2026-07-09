"""Known-card registry for RFID authentication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from database.db import db_cursor


@dataclass
class KnownCard:
    card_uid: str
    label: str
    active: bool = True
    notes: Optional[str] = None
    created_at: Optional[str] = None
    last_seen: Optional[str] = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()


def upsert_known_card(card: KnownCard) -> KnownCard:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO known_cards (card_uid, label, active, notes, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_uid) DO UPDATE SET
                label = excluded.label,
                active = excluded.active,
                notes = excluded.notes,
                last_seen = excluded.last_seen
            """,
            (
                card.card_uid,
                card.label,
                1 if card.active else 0,
                card.notes,
                card.created_at,
                card.last_seen,
            ),
        )
    return card


def list_known_cards() -> list[KnownCard]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM known_cards ORDER BY label ASC, card_uid ASC")
        rows = cur.fetchall()

    return [
        KnownCard(
            card_uid=row["card_uid"],
            label=row["label"],
            active=bool(row["active"]),
            notes=row["notes"],
            created_at=row["created_at"],
            last_seen=row["last_seen"],
        )
        for row in rows
    ]


def get_known_card(card_uid: str) -> Optional[KnownCard]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM known_cards WHERE card_uid = ?", (card_uid,))
        row = cur.fetchone()

    if row is None:
        return None

    return KnownCard(
        card_uid=row["card_uid"],
        label=row["label"],
        active=bool(row["active"]),
        notes=row["notes"],
        created_at=row["created_at"],
        last_seen=row["last_seen"],
    )


def touch_known_card(card_uid: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE known_cards SET last_seen = ? WHERE card_uid = ?",
            (datetime.now(timezone.utc).isoformat(), card_uid),
        )

