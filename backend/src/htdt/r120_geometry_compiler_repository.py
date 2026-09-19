from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .cad_repository import SceneRepository
from .cad_schema import ensure_native_schema
from .r120_geometry_compiler import (
    R120CompiledGeometry,
    R120LeakPortalDiagnostic,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class R120GeometryCompilerRepository:
    """Append-only persistence for solver-neutral R120 compiler authorities."""

    def __init__(self, scene_repository: SceneRepository) -> None:
        self.scene_repository = scene_repository
        self.path = Path(scene_repository.path)
        ensure_native_schema(self.path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cad_r120_compiled_geometry (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    compiled_geometry_id TEXT NOT NULL UNIQUE,
                    compiled_hash_sha256 TEXT NOT NULL UNIQUE,
                    scene_revision_id TEXT NOT NULL,
                    scene_revision_content_hash TEXT NOT NULL,
                    semantic_geometry_id TEXT NOT NULL,
                    semantic_geometry_hash_sha256 TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    FOREIGN KEY(scene_revision_id) REFERENCES scene_revisions(revision_id)
                );
                CREATE INDEX IF NOT EXISTS idx_r120_compiled_scene_revision
                    ON cad_r120_compiled_geometry(scene_revision_id, seq ASC);

                CREATE TABLE IF NOT EXISTS cad_r120_leak_portal_diagnostics (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    diagnostic_result_id TEXT NOT NULL UNIQUE,
                    diagnostic_hash_sha256 TEXT NOT NULL UNIQUE,
                    compiled_geometry_id TEXT NOT NULL,
                    compiled_geometry_hash_sha256 TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    FOREIGN KEY(compiled_geometry_id)
                        REFERENCES cad_r120_compiled_geometry(compiled_geometry_id)
                );
                CREATE INDEX IF NOT EXISTS idx_r120_leak_compiled_geometry
                    ON cad_r120_leak_portal_diagnostics(compiled_geometry_id, seq ASC);
                """
            )

    def save_compiled_geometry(
        self,
        compiled: R120CompiledGeometry,
    ) -> R120CompiledGeometry:
        compiled = R120CompiledGeometry.model_validate(
            compiled.model_dump(mode='python')
        )
        self._validate_scene_binding(compiled)

        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_compiled_geometry
                WHERE compiled_geometry_id=?
                """,
                (compiled.compiled_geometry_id,),
            ).fetchone()
            if existing is not None:
                persisted = R120CompiledGeometry.model_validate_json(
                    existing['payload_json']
                )
                if persisted != compiled:
                    raise ValueError(
                        'compiled geometry id already exists with different semantics'
                    )
                self._validate_scene_binding(persisted)
                return persisted

            hash_collision = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_compiled_geometry
                WHERE compiled_hash_sha256=?
                """,
                (compiled.compiled_hash_sha256,),
            ).fetchone()
            if hash_collision is not None:
                persisted = R120CompiledGeometry.model_validate_json(
                    hash_collision['payload_json']
                )
                if persisted != compiled:
                    raise ValueError(
                        'compiled geometry hash already exists with different semantics'
                    )
                self._validate_scene_binding(persisted)
                return persisted

            connection.execute(
                """
                INSERT INTO cad_r120_compiled_geometry(
                    compiled_geometry_id,
                    compiled_hash_sha256,
                    scene_revision_id,
                    scene_revision_content_hash,
                    semantic_geometry_id,
                    semantic_geometry_hash_sha256,
                    request_id,
                    payload_json,
                    recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    compiled.compiled_geometry_id,
                    compiled.compiled_hash_sha256,
                    compiled.exact_scene_revision_id,
                    compiled.exact_scene_revision_content_hash,
                    compiled.exact_semantic_geometry_id,
                    compiled.exact_semantic_geometry_hash_sha256,
                    compiled.request.request_id,
                    compiled.model_dump_json(),
                    _utc_now(),
                ),
            )
        return compiled

    def get_compiled_geometry(
        self,
        compiled_geometry_id: str,
    ) -> R120CompiledGeometry | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_compiled_geometry
                WHERE compiled_geometry_id=?
                """,
                (compiled_geometry_id,),
            ).fetchone()
        if row is None:
            return None
        compiled = R120CompiledGeometry.model_validate_json(row['payload_json'])
        self._validate_scene_binding(compiled)
        return compiled

    def get_compiled_geometry_by_hash(
        self,
        compiled_hash_sha256: str,
    ) -> R120CompiledGeometry | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_compiled_geometry
                WHERE compiled_hash_sha256=?
                """,
                (compiled_hash_sha256,),
            ).fetchone()
        if row is None:
            return None
        compiled = R120CompiledGeometry.model_validate_json(row['payload_json'])
        self._validate_scene_binding(compiled)
        return compiled

    def save_leak_portal_diagnostic(
        self,
        diagnostic: R120LeakPortalDiagnostic,
    ) -> R120LeakPortalDiagnostic:
        diagnostic = R120LeakPortalDiagnostic.model_validate(
            diagnostic.model_dump(mode='python')
        )
        compiled = self.get_compiled_geometry(
            diagnostic.exact_compiled_geometry_id
        )
        if compiled is None:
            raise ValueError(
                'leak/portal diagnostic references unpersisted compiled geometry'
            )
        if (
            compiled.compiled_hash_sha256
            != diagnostic.exact_compiled_geometry_hash_sha256
        ):
            raise ValueError(
                'leak/portal diagnostic compiled geometry hash mismatch'
            )

        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_leak_portal_diagnostics
                WHERE diagnostic_result_id=?
                """,
                (diagnostic.diagnostic_result_id,),
            ).fetchone()
            if existing is not None:
                persisted = R120LeakPortalDiagnostic.model_validate_json(
                    existing['payload_json']
                )
                if persisted != diagnostic:
                    raise ValueError(
                        'leak/portal diagnostic id already exists with different semantics'
                    )
                return persisted

            hash_collision = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_leak_portal_diagnostics
                WHERE diagnostic_hash_sha256=?
                """,
                (diagnostic.diagnostic_hash_sha256,),
            ).fetchone()
            if hash_collision is not None:
                persisted = R120LeakPortalDiagnostic.model_validate_json(
                    hash_collision['payload_json']
                )
                if persisted != diagnostic:
                    raise ValueError(
                        'leak/portal diagnostic hash already exists with different semantics'
                    )
                return persisted

            connection.execute(
                """
                INSERT INTO cad_r120_leak_portal_diagnostics(
                    diagnostic_result_id,
                    diagnostic_hash_sha256,
                    compiled_geometry_id,
                    compiled_geometry_hash_sha256,
                    request_id,
                    payload_json,
                    recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    diagnostic.diagnostic_result_id,
                    diagnostic.diagnostic_hash_sha256,
                    diagnostic.exact_compiled_geometry_id,
                    diagnostic.exact_compiled_geometry_hash_sha256,
                    diagnostic.request.request_id,
                    diagnostic.model_dump_json(),
                    _utc_now(),
                ),
            )
        return diagnostic

    def get_leak_portal_diagnostic(
        self,
        diagnostic_result_id: str,
    ) -> R120LeakPortalDiagnostic | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_r120_leak_portal_diagnostics
                WHERE diagnostic_result_id=?
                """,
                (diagnostic_result_id,),
            ).fetchone()
        if row is None:
            return None
        diagnostic = R120LeakPortalDiagnostic.model_validate_json(
            row['payload_json']
        )
        compiled = self.get_compiled_geometry(
            diagnostic.exact_compiled_geometry_id
        )
        if compiled is None:
            raise ValueError(
                'persisted leak/portal diagnostic references missing compiled geometry'
            )
        if (
            compiled.compiled_hash_sha256
            != diagnostic.exact_compiled_geometry_hash_sha256
        ):
            raise ValueError(
                'persisted leak/portal diagnostic compiled hash mismatch'
            )
        return diagnostic

    def _validate_scene_binding(
        self,
        compiled: R120CompiledGeometry,
    ) -> None:
        revision = self.scene_repository.get(
            compiled.exact_scene_revision_id
        )
        if revision is None:
            raise ValueError(
                'compiled geometry references an unpersisted SceneRevision'
            )
        if revision.content_hash != compiled.exact_scene_revision_content_hash:
            raise ValueError('compiled geometry SceneRevision content hash mismatch')
        geometry = revision.document.r120_semantic_geometry
        if geometry is None:
            raise ValueError(
                'compiled geometry SceneRevision no longer contains semantic geometry'
            )
        if geometry.geometry_id != compiled.exact_semantic_geometry_id:
            raise ValueError('compiled geometry SemanticAcousticGeometry id mismatch')
        if (
            geometry.semantic_hash_sha256
            != compiled.exact_semantic_geometry_hash_sha256
        ):
            raise ValueError(
                'compiled geometry SemanticAcousticGeometry hash mismatch'
            )
