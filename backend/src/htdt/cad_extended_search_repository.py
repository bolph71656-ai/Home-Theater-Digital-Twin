from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .cad_adaptive_planner import production_validation_ready
from .cad_extended_search import (
    CadExtendedModelCapability,
    CadExtendedSearchSpec,
    generate_extended_candidates,
)
from .cad_model_validation_repository import CadModelValidationRepository
from .cad_search import generate_cad_candidates
from .cad_search_repository import CadSearchRepository


class CadExtendedSearchRepository:
    """Immutable O80 capability/spec storage layered on base O10 SearchSpec authority."""

    def __init__(
        self,
        search_repository: CadSearchRepository,
        validation_repository: CadModelValidationRepository | None = None,
    ) -> None:
        self.search_repository = search_repository
        self.validation_repository = validation_repository
        self.path = Path(search_repository.path)
        if (
            validation_repository is not None
            and Path(validation_repository.path) != self.path
        ):
            raise ValueError(
                'extended search validation repository must share native CAD database'
            )
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
                CREATE TABLE IF NOT EXISTS cad_extended_model_capabilities (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id TEXT NOT NULL UNIQUE,
                    model_id TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    evidence_scope TEXT NOT NULL,
                    capability_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_extended_capability_model_seq
                    ON cad_extended_model_capabilities(model_id, model_version, seq ASC);

                CREATE TABLE IF NOT EXISTS cad_extended_search_specs (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    extended_search_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    base_search_spec_id TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    extended_search_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(base_search_spec_id)
                        REFERENCES cad_search_specs(search_spec_id),
                    FOREIGN KEY(capability_id)
                        REFERENCES cad_extended_model_capabilities(capability_id)
                );
                CREATE INDEX IF NOT EXISTS idx_extended_search_base_seq
                    ON cad_extended_search_specs(base_search_spec_id, seq ASC);
                """
            )

    def save_capability(self, capability: CadExtendedModelCapability) -> None:
        capability = CadExtendedModelCapability.model_validate(
            capability.model_dump(mode='python')
        )
        if capability.evidence_scope == 'owned_room':
            repository = self.validation_repository
            if repository is None:
                raise ValueError(
                    'owned-room extended capability requires validation repository'
                )
            if capability.validation_id is None:
                raise ValueError('owned-room extended capability has no ValidationRecord')
            validation = repository.get(capability.validation_id)
            if validation is None or not production_validation_ready(validation):
                raise ValueError(
                    'owned-room extended capability ValidationRecord is not eligible'
                )
            if (
                validation.model_id != capability.model_id
                or validation.model_version != capability.model_version
            ):
                raise ValueError(
                    'extended capability model does not match ValidationRecord'
                )

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO cad_extended_model_capabilities(
                    capability_id, model_id, model_version, evidence_scope,
                    capability_sha256, payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capability.capability_id,
                    capability.model_id,
                    capability.model_version,
                    capability.evidence_scope,
                    capability.capability_sha256,
                    capability.model_dump_json(),
                    capability.created_at_utc,
                ),
            )

    def get_capability(
        self,
        capability_id: str,
    ) -> CadExtendedModelCapability | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_extended_model_capabilities '
                'WHERE capability_id=?',
                (capability_id,),
            ).fetchone()
        return (
            None
            if row is None
            else CadExtendedModelCapability.model_validate_json(row['payload_json'])
        )

    def list_capabilities(self) -> tuple[CadExtendedModelCapability, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_extended_model_capabilities '
                'ORDER BY seq ASC'
            ).fetchall()
        return tuple(
            CadExtendedModelCapability.model_validate_json(row['payload_json'])
            for row in rows
        )

    def _base_page(self, spec) -> object:
        return generate_cad_candidates(
            self.search_repository.scene_repository,
            spec,
            offset=0,
            limit=1,
        )

    def save_spec(self, spec: CadExtendedSearchSpec) -> None:
        spec = CadExtendedSearchSpec.model_validate(spec.model_dump(mode='python'))
        base = self.search_repository.get(spec.base_search_spec_id)
        if base is None:
            raise ValueError('extended search base SearchSpec does not exist')
        if (
            base.document_id != spec.document_id
            or base.search_spec_sha256 != spec.base_search_spec_sha256
        ):
            raise ValueError('extended search base SearchSpec authority mismatch')
        source = self.search_repository.scene_repository.get(base.scene_revision_id)
        if (
            source is None
            or source.document_id != spec.document_id
            or source.content_hash != base.scene_content_hash
        ):
            raise ValueError('extended search source revision authority mismatch')

        capability = self.get_capability(spec.capability_id)
        if capability is None:
            raise ValueError('extended search model capability does not exist')
        if capability.capability_sha256 != spec.capability_sha256:
            raise ValueError('extended search model capability hash mismatch')

        page = self._base_page(base)
        if page.candidate_set_sha256 != spec.base_candidate_set_sha256:
            raise ValueError('extended search base candidate-set hash mismatch')

        # Full generation is the repository-level replay of axis/entity/capability
        # semantics and immutable candidate-limit authority.
        generate_extended_candidates(
            self.search_repository.scene_repository,
            base,
            spec,
            offset=0,
            limit=1,
        )

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO cad_extended_search_specs(
                    extended_search_id, document_id, base_search_spec_id,
                    capability_id, extended_search_sha256, payload_json,
                    created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec.extended_search_id,
                    spec.document_id,
                    spec.base_search_spec_id,
                    spec.capability_id,
                    spec.extended_search_sha256,
                    spec.model_dump_json(),
                    spec.created_at_utc,
                ),
            )

    def get_spec(self, extended_search_id: str) -> CadExtendedSearchSpec | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_extended_search_specs '
                'WHERE extended_search_id=?',
                (extended_search_id,),
            ).fetchone()
        return (
            None
            if row is None
            else CadExtendedSearchSpec.model_validate_json(row['payload_json'])
        )

    def list_for_base_search(
        self,
        base_search_spec_id: str,
    ) -> tuple[CadExtendedSearchSpec, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_extended_search_specs '
                'WHERE base_search_spec_id=? ORDER BY seq ASC',
                (base_search_spec_id,),
            ).fetchall()
        return tuple(
            CadExtendedSearchSpec.model_validate_json(row['payload_json'])
            for row in rows
        )
