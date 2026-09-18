from __future__ import annotations

from contextlib import closing
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


@dataclass(frozen=True)
class RecoverySnapshot:
    document_id: str
    source_revision_id: str | None
    updated_at_utc: str
    content_hash: str
    document: SceneDocument


@dataclass(frozen=True)
class EditorViewRecord:
    document_id: str
    selected_id: str | None
    selected_ids: tuple[str, ...]
    hidden_ids: tuple[str, ...]
    locked_ids: tuple[str, ...]


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
        with closing(self._connect()) as connection, connection:
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
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS scene_recovery_snapshots (
                    document_id TEXT PRIMARY KEY,
                    source_revision_id TEXT,
                    updated_at_utc TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(source_revision_id) REFERENCES scene_revisions(revision_id)
                )
                '''
            )
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS editor_view_states (
                    document_id TEXT PRIMARY KEY,
                    selected_id TEXT,
                    hidden_ids_json TEXT NOT NULL,
                    locked_ids_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                '''
            )
            columns = {row['name'] for row in connection.execute('PRAGMA table_info(editor_view_states)')}
            if 'selected_ids_json' not in columns:
                connection.execute(
                    "ALTER TABLE editor_view_states ADD COLUMN selected_ids_json TEXT NOT NULL DEFAULT '[]'"
                )

    def latest(self, document_id: str) -> SceneRevision | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT * FROM scene_revisions WHERE document_id=? ORDER BY seq DESC LIMIT 1',
                (document_id,),
            ).fetchone()
        return self._row_to_revision(row) if row else None

    def get(self, revision_id: str) -> SceneRevision | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT * FROM scene_revisions WHERE revision_id=?',
                (revision_id,),
            ).fetchone()
        return self._row_to_revision(row) if row else None

    def save(self, document: SceneDocument, *, parent_revision_id: str | None) -> SaveResult:
        payload_json = canonical_scene_json(document)
        content_hash = scene_content_hash(document)
        with closing(self._connect()) as connection, connection:
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
                    connection.execute(
                        'DELETE FROM scene_recovery_snapshots WHERE document_id=?',
                        (document.document_id,),
                    )
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
            connection.execute(
                'DELETE FROM scene_recovery_snapshots WHERE document_id=?',
                (document.document_id,),
            )
            row = connection.execute(
                'SELECT * FROM scene_revisions WHERE revision_id=?',
                (revision_id,),
            ).fetchone()
        return SaveResult(self._row_to_revision(row), created=True)

    def save_recovery(
        self,
        document: SceneDocument,
        *,
        source_revision_id: str | None,
    ) -> RecoverySnapshot | None:
        payload_json = canonical_scene_json(document)
        content_hash = scene_content_hash(document)
        updated_at = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            if source_revision_id is not None:
                source = connection.execute(
                    'SELECT * FROM scene_revisions WHERE revision_id=?',
                    (source_revision_id,),
                ).fetchone()
                if source is None:
                    raise ValueError(f'unknown recovery source revision: {source_revision_id}')
                if source['document_id'] != document.document_id:
                    raise ValueError('recovery source belongs to a different document')
                if source['content_hash'] == content_hash:
                    connection.execute(
                        'DELETE FROM scene_recovery_snapshots WHERE document_id=?',
                        (document.document_id,),
                    )
                    return None
            connection.execute(
                '''
                INSERT INTO scene_recovery_snapshots(
                    document_id, source_revision_id, updated_at_utc, content_hash, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    source_revision_id=excluded.source_revision_id,
                    updated_at_utc=excluded.updated_at_utc,
                    content_hash=excluded.content_hash,
                    payload_json=excluded.payload_json
                ''',
                (document.document_id, source_revision_id, updated_at, content_hash, payload_json),
            )
        return RecoverySnapshot(
            document_id=document.document_id,
            source_revision_id=source_revision_id,
            updated_at_utc=updated_at,
            content_hash=content_hash,
            document=document,
        )

    def recovery(self, document_id: str) -> RecoverySnapshot | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT * FROM scene_recovery_snapshots WHERE document_id=?',
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        document = SceneDocument.model_validate(json.loads(row['payload_json']))
        content_hash = scene_content_hash(document)
        if content_hash != row['content_hash']:
            raise ValueError(f'recovery snapshot hash mismatch: {document_id}')
        return RecoverySnapshot(
            document_id=row['document_id'],
            source_revision_id=row['source_revision_id'],
            updated_at_utc=row['updated_at_utc'],
            content_hash=row['content_hash'],
            document=document,
        )

    def clear_recovery(self, document_id: str) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                'DELETE FROM scene_recovery_snapshots WHERE document_id=?',
                (document_id,),
            )

    def save_view_state(
        self,
        document_id: str,
        *,
        selected_id: str | None,
        selected_ids: tuple[str, ...] | list[str] | None = None,
        hidden_ids: set[str],
        locked_ids: set[str],
    ) -> None:
        ordered_selected = list(dict.fromkeys(selected_ids or (() if selected_id is None else (selected_id,))))
        if selected_id is not None and selected_id not in ordered_selected:
            ordered_selected.append(selected_id)
        selected_json = json.dumps(ordered_selected, separators=(',', ':'))
        hidden_json = json.dumps(sorted(hidden_ids), separators=(',', ':'))
        locked_json = json.dumps(sorted(locked_ids), separators=(',', ':'))
        updated_at = datetime.now(timezone.utc).isoformat()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                '''
                INSERT INTO editor_view_states(
                    document_id, selected_id, selected_ids_json, hidden_ids_json, locked_ids_json, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    selected_id=excluded.selected_id,
                    selected_ids_json=excluded.selected_ids_json,
                    hidden_ids_json=excluded.hidden_ids_json,
                    locked_ids_json=excluded.locked_ids_json,
                    updated_at_utc=excluded.updated_at_utc
                ''',
                (document_id, selected_id, selected_json, hidden_json, locked_json, updated_at),
            )

    def view_state(self, document_id: str) -> EditorViewRecord | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT * FROM editor_view_states WHERE document_id=?',
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        selected = tuple(str(value) for value in json.loads(row['selected_ids_json']))
        if not selected and row['selected_id'] is not None:
            selected = (str(row['selected_id']),)
        hidden = tuple(str(value) for value in json.loads(row['hidden_ids_json']))
        locked = tuple(str(value) for value in json.loads(row['locked_ids_json']))
        return EditorViewRecord(
            document_id=row['document_id'],
            selected_id=row['selected_id'],
            selected_ids=selected,
            hidden_ids=hidden,
            locked_ids=locked,
        )

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
