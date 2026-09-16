from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .cad_scene import SceneDocument, canonical_scene_json, scene_content_hash


@dataclass(frozen=True)
class SceneRevision:
    revision_id: str
    document_id: str
    parent_revision_id: str | None
    created_at_utc: str
    content_hash: str
    document: SceneDocument


@dataclass(frozen=True)
class SaveResult:
    revision: SceneRevision
    created: bool


class SceneRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS scene_revisions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    parent_revision_id TEXT,
                    created_at_utc TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(parent_revision_id) REFERENCES scene_revisions(revision_id)
                )
                '''
            )
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_scene_revisions_document_seq '
                'ON scene_revisions(document_id, seq DESC)'
            )

    def latest(self, document_id: str) -> SceneRevision | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM scene_revisions WHERE document_id=? ORDER BY seq DESC LIMIT 1',
                (document_id,),
            ).fetchone()
        return self._row_to_revision(row) if row else None

    def get(self, revision_id: str) -> SceneRevision | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM scene_revisions WHERE revision_id=?',
                (revision_id,),
            ).fetchone()
        return self._row_to_revision(row) if row else None

    def save(self, document: SceneDocument, *, parent_revision_id: str | None) -> SaveResult:
        payload_json = canonical_scene_json(document)
        content_hash = scene_content_hash(document)
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            parent = None
            if parent_revision_id is not None:
                parent = connection.execute(
                    'SELECT * FROM scene_revisions WHERE revision_id=?',
                    (parent_revision_id,),
                ).fetchone()
                if parent is None:
                    raise ValueError(f'unknown parent revision: {parent_revision_id}')
                if parent['document_id'] != document.document_id:
                    raise ValueError('parent revision belongs to a different document')
                if parent['content_hash'] == content_hash:
                    return SaveResult(self._row_to_revision(parent), created=False)
            revision_id = str(uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                '''
                INSERT INTO scene_revisions(
                    revision_id, document_id, parent_revision_id, created_at_utc, content_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (revision_id, document.document_id, parent_revision_id, created_at, content_hash, payload_json),
            )
            row = connection.execute(
                'SELECT * FROM scene_revisions WHERE revision_id=?',
                (revision_id,),
            ).fetchone()
        return SaveResult(self._row_to_revision(row), created=True)

    @staticmethod
    def _row_to_revision(row: sqlite3.Row) -> SceneRevision:
        document = SceneDocument.model_validate(json.loads(row['payload_json']))
        content_hash = scene_content_hash(document)
        if content_hash != row['content_hash']:
            raise ValueError(f"scene revision hash mismatch: {row['revision_id']}")
        return SceneRevision(
            revision_id=row['revision_id'],
            document_id=row['document_id'],
            parent_revision_id=row['parent_revision_id'],
            created_at_utc=row['created_at_utc'],
            content_hash=row['content_hash'],
            document=document,
        )
