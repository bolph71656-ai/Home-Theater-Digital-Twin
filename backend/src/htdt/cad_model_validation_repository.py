from __future__ import annotations

from pathlib import Path
import sqlite3

from .cad_measurement_repository import CadMeasurementRepository
from .cad_model_validation import CadModelValidationRecord
from .cad_roomsim_repository import CadRoomSimRepository
from .cad_search_repository import CadSearchRepository


class CadModelValidationRepository:
    """Immutable O60 validation storage with cross-evidence authority checks."""

    def __init__(
        self,
        search_repository: CadSearchRepository,
        roomsim_repository: CadRoomSimRepository,
        measurement_repository: CadMeasurementRepository,
    ) -> None:
        self.search_repository = search_repository
        self.roomsim_repository = roomsim_repository
        self.measurement_repository = measurement_repository
        self.path = Path(search_repository.path)
        if Path(roomsim_repository.path) != self.path or Path(measurement_repository.path) != self.path:
            raise ValueError('O60 repositories must share one native CAD database')
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS cad_model_validations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    validation_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    search_spec_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    recommendation_gate TEXT NOT NULL,
                    validation_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    FOREIGN KEY(search_spec_id) REFERENCES cad_search_specs(search_spec_id)
                );
                CREATE INDEX IF NOT EXISTS idx_model_validation_search_seq
                    ON cad_model_validations(search_spec_id, seq ASC);
                '''
            )

    def save(self, record: CadModelValidationRecord) -> None:
        spec = self.search_repository.get(record.search_spec_id)
        if spec is None:
            raise ValueError('model validation SearchSpec does not exist')
        if spec.document_id != record.document_id or spec.search_spec_sha256 != record.search_spec_sha256:
            raise ValueError('model validation SearchSpec authority mismatch')

        plans = self.measurement_repository.list_measurement_plans(record.search_spec_id)
        for pair in record.pairs:
            attempt = self.roomsim_repository.get_attempt(pair.prediction_source_id)
            if attempt is None or attempt.status != 'completed':
                raise ValueError('validation prediction must reference a completed Room Simulator attempt')
            if attempt.candidate_id != pair.candidate_id:
                raise ValueError('validation prediction candidate mismatch')
            batch = self.roomsim_repository.get_batch_spec(attempt.batch_run_id)
            if batch is None:
                raise ValueError('validation prediction batch does not exist')
            if (
                batch.document_id != record.document_id
                or batch.search_spec_id != record.search_spec_id
                or batch.search_spec_sha256 != record.search_spec_sha256
                or batch.candidate_set_sha256 != record.candidate_set_sha256
                or batch.model_id != record.model_id
            ):
                raise ValueError('validation prediction batch authority mismatch')
            if attempt.model_version != record.model_version:
                raise ValueError('validation prediction model version mismatch')

            measurement = self.measurement_repository.get_measurement(pair.measurement_id)
            if measurement is None or measurement.evidence_type != 'measured':
                raise ValueError('validation measurement must reference measured evidence')
            linked = any(
                plan.status == 'measured'
                and plan.candidate_id == pair.candidate_id
                and plan.candidate_set_sha256 == record.candidate_set_sha256
                and pair.measurement_id in plan.measurement_ids
                for plan in plans
            )
            if not linked:
                raise ValueError('validation measurement is not linked to the candidate Measurement Plan')

        with self._connect() as connection:
            connection.execute(
                '''INSERT INTO cad_model_validations(
                    validation_id, document_id, search_spec_id, model_id, model_version,
                    recommendation_gate, validation_sha256, payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    record.validation_id,
                    record.document_id,
                    record.search_spec_id,
                    record.model_id,
                    record.model_version,
                    record.recommendation_gate,
                    record.validation_sha256,
                    record.model_dump_json(),
                    record.created_at_utc,
                ),
            )

    def get(self, validation_id: str) -> CadModelValidationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT payload_json FROM cad_model_validations WHERE validation_id=?',
                (validation_id,),
            ).fetchone()
        return None if row is None else CadModelValidationRecord.model_validate_json(row['payload_json'])

    def list_for_search_spec(self, search_spec_id: str) -> tuple[CadModelValidationRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT payload_json FROM cad_model_validations WHERE search_spec_id=? ORDER BY seq ASC',
                (search_spec_id,),
            ).fetchall()
        return tuple(CadModelValidationRecord.model_validate_json(row['payload_json']) for row in rows)
