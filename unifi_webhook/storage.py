from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator

from .payload import Client


@dataclass(frozen=True)
class Sighting:
    is_new: bool
    sightings: int


class ClientStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def register_sighting(self, client: Client, payload: dict[str, Any]) -> Sighting:
        now = _utc_now()
        serialized_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO clients (
                    mac, first_seen_at, last_seen_at, sightings, name, ip_address,
                    network, wifi_name, connected_to, site, manufacturer,
                    notification_status, first_payload, last_payload
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    client.mac,
                    now,
                    now,
                    client.name,
                    client.ip_address,
                    client.network,
                    client.wifi_name,
                    client.connected_to,
                    client.site,
                    client.manufacturer,
                    serialized_payload,
                    serialized_payload,
                ),
            )
            is_new = cursor.rowcount == 1
            if not is_new:
                connection.execute(
                    """
                    UPDATE clients
                    SET last_seen_at = ?, sightings = sightings + 1,
                        name = ?, ip_address = ?, network = ?, wifi_name = ?,
                        connected_to = ?, site = ?, manufacturer = ?, last_payload = ?
                    WHERE mac = ?
                    """,
                    (
                        now,
                        client.name,
                        client.ip_address,
                        client.network,
                        client.wifi_name,
                        client.connected_to,
                        client.site,
                        client.manufacturer,
                        serialized_payload,
                        client.mac,
                    ),
                )
            row = connection.execute("SELECT sightings FROM clients WHERE mac = ?", (client.mac,)).fetchone()
            connection.commit()
        return Sighting(is_new=is_new, sightings=int(row[0]))

    def seed_clients(self, clients: Iterable[Client]) -> int:
        now = _utc_now()
        rows = [
            (
                client.mac,
                now,
                now,
                client.name,
                client.ip_address,
                client.network,
                client.wifi_name,
                client.connected_to,
                client.site,
                client.manufacturer,
            )
            for client in clients
        ]
        if not rows:
            return 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changes_before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO clients (
                    mac, first_seen_at, last_seen_at, sightings, name, ip_address,
                    network, wifi_name, connected_to, site, manufacturer,
                    notification_status, first_payload, last_payload
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 'seeded', '{}', '{}')
                """,
                rows,
            )
            seeded = connection.total_changes - changes_before
            connection.commit()
        return seeded

    def mark_notification(self, mac: str, status: str, error: str = "") -> None:
        if status not in {"delivered", "failed"}:
            raise ValueError("notification status must be delivered or failed")
        delivered_at = _utc_now() if status == "delivered" else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE clients
                SET notification_status = ?, notification_attempted_at = ?,
                    notification_delivered_at = ?, notification_error = ?
                WHERE mac = ?
                """,
                (status, _utc_now(), delivered_at, error[:2000], mac),
            )

    def client_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM clients").fetchone()
        return int(row[0])

    def get_client(self, mac: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM clients WHERE mac = ?", (mac,)).fetchone()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    mac TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    sightings INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    network TEXT NOT NULL,
                    wifi_name TEXT NOT NULL,
                    connected_to TEXT NOT NULL,
                    site TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    notification_status TEXT NOT NULL,
                    notification_attempted_at TEXT,
                    notification_delivered_at TEXT,
                    notification_error TEXT NOT NULL DEFAULT '',
                    first_payload TEXT NOT NULL,
                    last_payload TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
