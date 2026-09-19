from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .cad_directivity import (
    DirectivityDataset,
    validate_directivity_dataset_binding,
)
from .cad_equipment_repository import CadEquipmentRepository
from .cad_repository import SceneRepository
from .cad_schema import ensure_native_schema


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CadDirectivityRepository:
    """Append-only persistence for exact O100C DirectivityDataset authority."""

    def __init__(
        self,
        scene_repository: SceneRepository,
        equipment_repository: CadEquipmentRepository | None = None,
    ) -> None:
        self.scene_repository = scene_repository
        self.equipment_repository = (
            equipment_repository
            if equipment_repository is not None
            else CadEquipmentRepository(scene_repository)
        )
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
                CREATE TABLE IF NOT EXISTS cad_directivity_datasets (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    equipment_definition_sha256 TEXT NOT NULL,
                    source_asset_sha256 TEXT NOT NULL,
                    semantic_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    UNIQUE(dataset_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_directivity_dataset_seq
                    ON cad_directivity_datasets(seq ASC);
                CREATE INDEX IF NOT EXISTS idx_directivity_dataset_equipment
                    ON cad_directivity_datasets(equipment_definition_sha256, seq ASC);
                """
            )

    def save_dataset(
        self,
        dataset: DirectivityDataset,
    ) -> DirectivityDataset:
        dataset = DirectivityDataset.model_validate(
            dataset.model_dump(mode='python')
        )
        definition = self.equipment_repository.get_definition_by_hash(
            dataset.equipment_definition_sha256
        )
        if definition is None:
            raise ValueError(
                'DirectivityDataset references an unpersisted EquipmentDefinition'
            )
        validate_directivity_dataset_binding(dataset, definition)

        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                """
                SELECT payload_json
                FROM cad_directivity_datasets
                WHERE dataset_id=? AND version=?
                """,
                (dataset.dataset_id, dataset.version),
            ).fetchone()
            if existing is not None:
                persisted = DirectivityDataset.model_validate_json(
                    existing['payload_json']
                )
                if persisted != dataset:
                    raise ValueError(
                        'directivity dataset id/version already exists with different semantics'
                    )
                return persisted
            connection.execute(
                """
                INSERT INTO cad_directivity_datasets(
                    dataset_id, version,
                    equipment_definition_sha256,
                    source_asset_sha256,
                    semantic_sha256,
                    payload_json,
                    recorded_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset.dataset_id,
                    dataset.version,
                    dataset.equipment_definition_sha256,
                    dataset.source_asset_sha256,
                    dataset.semantic_sha256,
                    dataset.model_dump_json(),
                    _utc_now(),
                ),
            )
        return dataset

    def get_dataset(
        self,
        dataset_id: str,
        version: str,
    ) -> DirectivityDataset | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_directivity_datasets
                WHERE dataset_id=? AND version=?
                """,
                (dataset_id, version),
            ).fetchone()
        if row is None:
            return None
        dataset = DirectivityDataset.model_validate_json(row['payload_json'])
        definition = self.equipment_repository.get_definition_by_hash(
            dataset.equipment_definition_sha256
        )
        if definition is None:
            raise ValueError(
                'persisted DirectivityDataset references missing EquipmentDefinition'
            )
        validate_directivity_dataset_binding(dataset, definition)
        return dataset

    def get_dataset_by_hash(
        self,
        semantic_sha256: str,
    ) -> DirectivityDataset | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM cad_directivity_datasets
                WHERE semantic_sha256=?
                """,
                (semantic_sha256,),
            ).fetchone()
        if row is None:
            return None
        dataset = DirectivityDataset.model_validate_json(row['payload_json'])
        definition = self.equipment_repository.get_definition_by_hash(
            dataset.equipment_definition_sha256
        )
        if definition is None:
            raise ValueError(
                'persisted DirectivityDataset references missing EquipmentDefinition'
            )
        validate_directivity_dataset_binding(dataset, definition)
        return dataset

    def list_datasets_for_definition(
        self,
        equipment_definition_sha256: str,
    ) -> tuple[DirectivityDataset, ...]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM cad_directivity_datasets
                WHERE equipment_definition_sha256=?
                ORDER BY seq ASC
                """,
                (equipment_definition_sha256,),
            ).fetchall()
        datasets = tuple(
            DirectivityDataset.model_validate_json(row['payload_json'])
            for row in rows
        )
        definition = self.equipment_repository.get_definition_by_hash(
            equipment_definition_sha256
        )
        if datasets and definition is None:
            raise ValueError(
                'persisted DirectivityDataset references missing EquipmentDefinition'
            )
        if definition is not None:
            for dataset in datasets:
                validate_directivity_dataset_binding(dataset, definition)
        return datasets
