"""SQLite persistence for reviewed word-bank entries."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class WordBankRepository:
    """Own the SQLite connection and word-bank schema only."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_word TEXT NOT NULL UNIQUE,
                    word TEXT NOT NULL,
                    decoding TEXT NOT NULL,
                    formatted TEXT NOT NULL,
                    syllables_json TEXT NOT NULL,
                    syllable_count INTEGER NOT NULL,
                    stressed_syllable_index INTEGER NOT NULL DEFAULT 0,
                    pos TEXT,
                    family TEXT,
                    cefr TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'rule-based',
                    is_academic INTEGER NOT NULL DEFAULT 0,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS word_syllables (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL,
                    syllable TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS word_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL UNIQUE,
                    pos TEXT,
                    family TEXT,
                    notes TEXT,
                    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academic_families (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    description TEXT
                );
                CREATE TABLE IF NOT EXISTS academic_family_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    family_id INTEGER NOT NULL,
                    word_id INTEGER NOT NULL,
                    FOREIGN KEY (family_id) REFERENCES academic_families(id) ON DELETE CASCADE,
                    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE,
                    UNIQUE (family_id, word_id)
                );
                """
            )

    def lookup(self, normalized_word: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM words WHERE normalized_word = ?",
                (normalized_word,),
            ).fetchone()
        return self._row_to_result(row) if row else None

    def list_words(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM words ORDER BY word ASC").fetchall()
        return [self._row_to_result(row) for row in rows]

    def save(self, record: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM words WHERE normalized_word = ?",
                (record["normalized_word"],),
            ).fetchone()
            values = (
                record["normalized_word"], record["word"], record["decoding"], record["formatted"],
                json.dumps(record["syllables"]), len(record["syllables"]), record["stressed_syllable_index"],
                record.get("pos"), record.get("family"), record["cefr"], record["source"],
                int(bool(record["is_academic"])), record.get("notes"),
            )
            if existing:
                connection.execute(
                    """UPDATE words SET word=?, decoding=?, formatted=?, syllables_json=?,
                    syllable_count=?, stressed_syllable_index=?, pos=?, family=?, cefr=?, source=?,
                    is_academic=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (*values[1:], existing["id"]),
                )
                word_id = existing["id"]
            else:
                cursor = connection.execute(
                    """INSERT INTO words (normalized_word, word, decoding, formatted, syllables_json,
                    syllable_count, stressed_syllable_index, pos, family, cefr, source, is_academic, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                word_id = cursor.lastrowid
            connection.execute("DELETE FROM word_syllables WHERE word_id = ?", (word_id,))
            connection.executemany(
                "INSERT INTO word_syllables (word_id, syllable, ordinal) VALUES (?, ?, ?)",
                [(word_id, syllable, index) for index, syllable in enumerate(record["syllables"])],
            )
            connection.execute(
                """INSERT INTO word_metadata (word_id, pos, family, notes) VALUES (?, ?, ?, ?)
                ON CONFLICT(word_id) DO UPDATE SET pos=excluded.pos, family=excluded.family, notes=excluded.notes""",
                (word_id, record.get("pos"), record.get("family"), record.get("notes")),
            )
        saved = self.lookup(record["normalized_word"])
        if saved is None:
            raise LookupError(f"Failed to persist word '{record['word']}' to the word bank.")
        return saved

    @staticmethod
    def _row_to_result(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "word": row["word"], "normalized_word": row["normalized_word"],
            "syllables": json.loads(row["syllables_json"]),
            "stressed_syllable_index": row["stressed_syllable_index"], "decoding": row["decoding"],
            "formatted": row["formatted"], "cefr": row["cefr"], "pos": row["pos"],
            "family": row["family"], "source": row["source"], "is_academic": bool(row["is_academic"]),
            "notes": row["notes"], "from_word_bank": True,
        }


__all__ = ["WordBankRepository"]
