from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from .cad_acoustic_treatment import (
    AcousticTreatmentDefinition,
    AcousticTreatmentPlacement,
    TreatmentSurfaceBindingEvaluation,
    evaluate_treatment_surface_binding,
)
from .cad_repository import SceneRepository
from .cad_schema import check_native_schema_compatibility
from .cad_system_variant_repository import CadSystemVariantRepository


class CadAcousticTreatmentRepository:
    """Append-only persistence for immutable treatment definitions and placements."""

    def __init__(
        self,
        scene_repository: SceneRepository,
        system_variant_repository: CadSystemVariantRepository | None = None,
    ) -> None:
        self.scene_repository = scene_repository
        self.system_variant_repository = system_variant_repository
        self.path = Path(scene_repository.path)
        check_native_schema_compatibility(self.path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        check_native_schema_compatibility(self.path)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cad_acoustic_treatment_definitions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    definition_id TEXT NOT NULL,
                    definition_version TEXT NOT NULL,
                    definition_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    UNIQUE(definition_id, definition_version)
                );
                CREATE INDEX IF NOT EXISTS idx_acoustic_treatment_definition_id_seq
                    ON cad_acoustic_treatment_definitions(definition_id, seq ASC);

                CREATE TABLE IF NOT EXISTS cad_acoustic_treatment_placements (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    instance_id TEXT NOT NULL,
                    placement_version INTEGER NOT NULL,
                    lifecycle TEXT NOT NULL,
                    definition_id TEXT NOT NULL,
                    definition_version TEXT NOT NULL,
                    definition_sha256 TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    scene_revision_id TEXT NOT NULL,
                    system_variant_id TEXT,
                    placement_sha256 TEXT NOT NULL UNIQUE,
                    previous_placement_sha256 TEXT,
                    payload_json TEXT NOT NULL,
                    UNIQUE(instance_id, placement_version),
                    FOREIGN KEY(definition_id, definition_version)
                        REFERENCES cad_acoustic_treatment_definitions(definition_id, definition_version),
                    FOREIGN KEY(scene_revision_id)
                        REFERENCES scene_revisions(revision_id),
                    FOREIGN KEY(system_variant_id)
                        REFERENCES cad_system_variants(variant_id),
                    FOREIGN KEY(previous_placement_sha256)
                        REFERENCES cad_acoustic_treatment_placements(placement_sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_acoustic_treatment_placement_scene_seq
                    ON cad_acoustic_treatment_placements(scene_revision_id, seq ASC);
                CREATE INDEX IF NOT EXISTS idx_acoustic_treatment_placement_variant_seq
                    ON cad_acoustic_treatment_placements(system_variant_id, seq ASC);
                CREATE INDEX IF NOT EXISTS idx_acoustic_treatment_placement_instance_seq
                    ON cad_acoustic_treatment_placements(instance_id, placement_version ASC);
                """
            )

    def save_definition(
        self,
        definition: AcousticTreatmentDefinition,
    ) -> AcousticTreatmentDefinition:
        definition = AcousticTreatmentDefinition.model_validate(
            definition.model_dump(mode='python')
        )
        existing = self.get_definition(definition.definition_id, definition.version)
        if existing is not None:
            if existing.definition_sha256 != definition.definition_sha256:
                raise ValueError('AcousticTreatmentDefinition version is immutable')
            return existing

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO cad_acoustic_treatment_definitions(
                    definition_id, definition_version, definition_sha256, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    definition.definition_id,
                    definition.version,
                    definition.definition_sha256,
                    definition.model_dump_json(),
                ),
            )
        return definition

    def get_definition(
        self,
        definition_id: str,
        version: str,
    ) -> AcousticTreatmentDefinition | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_acoustic_treatment_definitions '
                'WHERE definition_id=? AND definition_version=?',
                (definition_id, version),
            ).fetchone()
        if row is None:
            return None
        return AcousticTreatmentDefinition.model_validate_json(row['payload_json'])

    def list_definition_versions(
        self,
        definition_id: str,
    ) -> tuple[AcousticTreatmentDefinition, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_acoustic_treatment_definitions '
                'WHERE definition_id=? ORDER BY seq ASC',
                (definition_id,),
            ).fetchall()
        return tuple(
            AcousticTreatmentDefinition.model_validate_json(row['payload_json'])
            for row in rows
        )

    def evaluate_placement_surface_binding(
        self,
        placement: AcousticTreatmentPlacement,
        *,
        scene_revision_id: str | None = None,
    ) -> TreatmentSurfaceBindingEvaluation:
        bound_revision = self.scene_repository.get(placement.scene_revision_id)
        evaluated_revision_id = (
            placement.scene_revision_id
            if scene_revision_id is None
            else scene_revision_id
        )
        evaluated_revision = self.scene_repository.get(evaluated_revision_id)
        return evaluate_treatment_surface_binding(
            placement,
            bound_revision=bound_revision,
            evaluated_revision=evaluated_revision,
            evaluated_revision_id=evaluated_revision_id,
        )

    def _decode_placement(self, payload_json: str) -> AcousticTreatmentPlacement:
        placement = AcousticTreatmentPlacement.model_validate_json(payload_json)
        revision = self.scene_repository.get(placement.scene_revision_id)
        if (
            placement.host_surface_id is not None
            and revision is not None
            and revision.document.r120_semantic_geometry is not None
        ):
            evaluation = self.evaluate_placement_surface_binding(placement)
            if not evaluation.placement_authority_valid:
                raise ValueError(
                    'persisted treatment placement semantic host binding is invalid: '
                    f'{evaluation.binding_state}'
                )
        return placement

    def _validate_placement_authority(
        self,
        placement: AcousticTreatmentPlacement,
    ) -> None:
        definition = self.get_definition(
            placement.definition_id,
            placement.definition_version,
        )
        if definition is None:
            raise ValueError('treatment placement references an unsaved definition')
        if definition.definition_sha256 != placement.definition_sha256:
            raise ValueError('treatment placement definition semantic hash mismatch')

        revision = self.scene_repository.get(placement.scene_revision_id)
        if revision is None:
            raise ValueError('treatment placement SceneRevision does not exist')
        if (
            revision.document_id != placement.document_id
            or revision.content_hash != placement.scene_content_hash
        ):
            raise ValueError('treatment placement SceneRevision authority mismatch')

        if (
            placement.host_surface_id is not None
            and revision.document.r120_semantic_geometry is not None
        ):
            evaluation = self.evaluate_placement_surface_binding(placement)
            if not evaluation.placement_authority_valid:
                raise ValueError(
                    'treatment placement semantic host binding is invalid: '
                    f'{evaluation.binding_state}'
                )

        if placement.system_variant_id is not None:
            if self.system_variant_repository is None:
                raise ValueError(
                    'SystemVariant-bound treatment placement requires CadSystemVariantRepository'
                )
            variant = self.system_variant_repository.get_variant(placement.system_variant_id)
            if variant is None:
                raise ValueError('treatment placement SystemVariant does not exist')
            if (
                variant.variant_sha256 != placement.system_variant_sha256
                or variant.document_id != placement.document_id
            ):
                raise ValueError('treatment placement SystemVariant authority mismatch')
            if placement.system_variant_relation == 'proposal_baseline' and (
                variant.baseline_revision_id != revision.revision_id
                or variant.baseline_content_hash != revision.content_hash
            ):
                raise ValueError('proposed treatment placement baseline is not exact')

        if placement.placement_version == 1:
            if (
                placement.previous_placement_version is not None
                or placement.previous_placement_sha256 is not None
            ):
                raise ValueError('first treatment placement version cannot have lineage')
            return

        previous = self.get_placement(
            placement.instance_id,
            placement.placement_version - 1,
        )
        if previous is None:
            raise ValueError('treatment placement prior lineage does not exist')
        if previous.placement_sha256 != placement.previous_placement_sha256:
            raise ValueError('treatment placement prior lineage hash mismatch')
        if (
            previous.instance_id != placement.instance_id
            or previous.definition_id != placement.definition_id
            or previous.definition_version != placement.definition_version
            or previous.definition_sha256 != placement.definition_sha256
            or previous.document_id != placement.document_id
        ):
            raise ValueError('treatment placement lineage changed immutable authority')
        if previous.lifecycle == 'installed':
            raise ValueError('installed treatment placement is terminal')
        if placement.lifecycle not in {'proposed', 'installed'}:
            raise ValueError('unsupported treatment lifecycle transition')

    def save_placement(
        self,
        placement: AcousticTreatmentPlacement,
    ) -> AcousticTreatmentPlacement:
        placement = AcousticTreatmentPlacement.model_validate(
            placement.model_dump(mode='python')
        )
        self._validate_placement_authority(placement)

        existing = self.get_placement(
            placement.instance_id,
            placement.placement_version,
        )
        if existing is not None:
            if existing.placement_sha256 != placement.placement_sha256:
                raise ValueError('treatment placement version is immutable')
            return existing

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO cad_acoustic_treatment_placements(
                    instance_id, placement_version, lifecycle,
                    definition_id, definition_version, definition_sha256,
                    document_id, scene_revision_id, system_variant_id,
                    placement_sha256, previous_placement_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    placement.instance_id,
                    placement.placement_version,
                    placement.lifecycle,
                    placement.definition_id,
                    placement.definition_version,
                    placement.definition_sha256,
                    placement.document_id,
                    placement.scene_revision_id,
                    placement.system_variant_id,
                    placement.placement_sha256,
                    placement.previous_placement_sha256,
                    placement.model_dump_json(),
                ),
            )
        return placement

    def get_placement(
        self,
        instance_id: str,
        placement_version: int,
    ) -> AcousticTreatmentPlacement | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_acoustic_treatment_placements '
                'WHERE instance_id=? AND placement_version=?',
                (instance_id, placement_version),
            ).fetchone()
        if row is None:
            return None
        return self._decode_placement(row['payload_json'])

    def latest_placement(
        self,
        instance_id: str,
    ) -> AcousticTreatmentPlacement | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_acoustic_treatment_placements '
                'WHERE instance_id=? ORDER BY placement_version DESC LIMIT 1',
                (instance_id,),
            ).fetchone()
        if row is None:
            return None
        return self._decode_placement(row['payload_json'])

    def list_placements_for_scene(
        self,
        scene_revision_id: str,
    ) -> tuple[AcousticTreatmentPlacement, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_acoustic_treatment_placements '
                'WHERE scene_revision_id=? ORDER BY seq ASC',
                (scene_revision_id,),
            ).fetchall()
        return tuple(self._decode_placement(row['payload_json']) for row in rows)

    def list_placements_for_variant(
        self,
        system_variant_id: str,
    ) -> tuple[AcousticTreatmentPlacement, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_acoustic_treatment_placements '
                'WHERE system_variant_id=? ORDER BY seq ASC',
                (system_variant_id,),
            ).fetchall()
        return tuple(self._decode_placement(row['payload_json']) for row in rows)
