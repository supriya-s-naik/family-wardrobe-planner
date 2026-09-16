from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from wardrobe_planner.data.seed_loader import validate_references
from wardrobe_planner.domain.models import Event, SeedDataset, WardrobeItem, WeatherSnapshot


class SQLiteApplicationStore:
    """Persistent application state layered over the versioned demo seed data."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    @classmethod
    def from_env(cls, default_path: str | Path) -> SQLiteApplicationStore:
        return cls(os.getenv("WARDROBE_DB_PATH") or default_path)

    def initialize(self, seed: SeedDataset) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS wardrobe_items (
                    id TEXT PRIMARY KEY,
                    member_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    image_bytes BLOB,
                    image_media_type TEXT,
                    seed_order INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS wardrobe_items_member_idx
                ON wardrobe_items(member_id);

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL,
                    weather_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    seed_order INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS weather_snapshots (
                    key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    seed_order INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO wardrobe_items
                    (id, member_id, payload_json, seed_order)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (item.id, item.member_id, item.model_dump_json(), position)
                    for position, item in enumerate(seed.wardrobe_items)
                ],
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO weather_snapshots (key, payload_json, seed_order)
                VALUES (?, ?, ?)
                """,
                [
                    (weather.key, weather.model_dump_json(), position)
                    for position, weather in enumerate(seed.weather)
                ],
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO events
                    (id, household_id, weather_key, payload_json, seed_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.id,
                        event.household_id,
                        event.weather_key,
                        event.model_dump_json(),
                        position,
                    )
                    for position, event in enumerate(seed.events)
                ],
            )

    def load_dataset(self, seed: SeedDataset) -> SeedDataset:
        dataset = seed.model_copy(deep=True)
        with self._connection() as connection:
            item_rows = connection.execute(
                """
                SELECT payload_json FROM wardrobe_items
                ORDER BY seed_order IS NULL, seed_order, created_at, id
                """
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT payload_json FROM events
                ORDER BY seed_order IS NULL, seed_order, created_at, id
                """
            ).fetchall()
            weather_rows = connection.execute(
                """
                SELECT payload_json FROM weather_snapshots
                ORDER BY seed_order IS NULL, seed_order, created_at, key
                """
            ).fetchall()

        dataset.wardrobe_items = [
            WardrobeItem.model_validate_json(row["payload_json"]) for row in item_rows
        ]
        dataset.events = [Event.model_validate_json(row["payload_json"]) for row in event_rows]
        dataset.weather = [
            WeatherSnapshot.model_validate_json(row["payload_json"]) for row in weather_rows
        ]
        validate_references(dataset)
        return dataset

    def save_wardrobe_item(
        self,
        item: WardrobeItem,
        *,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO wardrobe_items
                    (id, member_id, payload_json, image_bytes, image_media_type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    member_id = excluded.member_id,
                    payload_json = excluded.payload_json,
                    image_bytes = COALESCE(excluded.image_bytes, wardrobe_items.image_bytes),
                    image_media_type = COALESCE(
                        excluded.image_media_type,
                        wardrobe_items.image_media_type
                    ),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    item.id,
                    item.member_id,
                    item.model_dump_json(),
                    image_bytes,
                    image_media_type,
                ),
            )

    def set_wardrobe_item_availability(self, item_id: str, available: bool) -> WardrobeItem:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM wardrobe_items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown wardrobe item: {item_id}")
            item = WardrobeItem.model_validate_json(row["payload_json"]).model_copy(
                update={"available": available}
            )
            connection.execute(
                """
                UPDATE wardrobe_items
                SET payload_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (item.model_dump_json(), item_id),
            )
        return item

    def get_wardrobe_image(self, item_id: str) -> bytes | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT image_bytes FROM wardrobe_items WHERE id = ?", (item_id,)
            ).fetchone()
        if row is None or row["image_bytes"] is None:
            return None
        return bytes(row["image_bytes"])

    def save_event(self, event: Event, weather: WeatherSnapshot) -> None:
        if event.weather_key != weather.key:
            raise ValueError("Event weather key must match the weather snapshot key")
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO weather_snapshots (key, payload_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (weather.key, weather.model_dump_json()),
            )
            connection.execute(
                """
                INSERT INTO events (id, household_id, weather_key, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    household_id = excluded.household_id,
                    weather_key = excluded.weather_key,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    event.id,
                    event.household_id,
                    event.weather_key,
                    event.model_dump_json(),
                ),
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()
