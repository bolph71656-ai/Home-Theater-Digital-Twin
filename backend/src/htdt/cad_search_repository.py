from __future__ import annotations

from pathlib import Path
import sqlite3

from .cad_repository import SceneRepository
from .cad_search_models import CadSearchSpec


class CadSearchRepository:
    """Immutable native SearchSpec storage beside SceneRevision authority."""

    def __init__(self, scene_repository: SceneRepository) -> None:
        self.scene_repository = scene_repository
        self.path = Path(scene_repository.path)
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
                CREATE TABLE IF NOT EXISTS cad_search_specs (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_spec_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    scene_revision_id TEXT NOT NULL,
                    scene_content_hash TEXT NOT NULL,
                    constraint_workspace_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    search_spec_sha256 TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(scene_revision_id) REFERENCES scene_revisions(revision_id)
                )
                '''
            )
            connection.execute(
                'CREATE INDEX IF NOT EXISTS idx_cad_search_document_seq '
                'ON cad_search_specs(document_id, seq DESC)'
            )

    def save(self, spec: CadSearchSpec) -> None:
        source = self.scene_repository.get(spec.scene_revision_id)
        if source is None:
            raise ValueError('SearchSpec source revision does not exist')
        if source.document_id != spec.document_id:
            raise ValueError('SearchSpec source revision belongs to another document')
        if source.content_hash != spec.scene_content_hash:
            raise ValueError('SearchSpec source content hash does not match revision')

        payload_json = spec.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                '''
                INSERT INTO cad_search_specs(
                    search_spec_id, document_id, scene_revision_id, scene_content_hash,
                    constraint_workspace_hash, payload_json, search_spec_sha256, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    spec.search_spec_id,
                    spec.document_id,
                    spec.scene_revision_id,
                    spec.scene_content_hash,
                    spec.constraint_workspace_hash,
                    payload_json,
                    spec.search_spec_sha256,
                    spec.created_at_utc,
                ),
            )

    def get(self, search_spec_id: str) -> CadSearchSpec | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_search_specs WHERE search_spec_id=?',
                (search_spec_id,),
            ).fetchone()
        return None if row is None else CadSearchSpec.model_validate_json(row['payload_json'])

    def list_specs(self, document_id: str) -> tuple[CadSearchSpec, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_search_specs WHERE document_id=? ORDER BY seq ASC',
                (document_id,),
            ).fetchall()
        return tuple(CadSearchSpec.model_validate_json(row['payload_json']) for row in rows)
