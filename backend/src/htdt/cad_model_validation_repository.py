from __future__ import annotations

from math import sqrt
from pathlib import Path
import sqlite3

from .cad_measurement_repository import CadMeasurementRepository
from .cad_model_validation import CadModelValidationRecord
from .cad_objective_repository import CadObjectiveRepository
from .cad_roomsim_repository import CadRoomSimRepository
from .cad_search import generate_cad_candidates
from .cad_search_repository import CadSearchRepository
from .cad_validation_metrics import (
    build_candidate_separation_check,
    build_repeatability_check,
    build_sensitivity_check,
)
from .comparison import FrequencyResponse


class CadModelValidationRepository:
    """Immutable O60 validation storage with cross-evidence authority checks."""

    def __init__(
        self,
        search_repository: CadSearchRepository,
        roomsim_repository: CadRoomSimRepository,
        measurement_repository: CadMeasurementRepository,
        objective_repository: CadObjectiveRepository | None = None,
    ) -> None:
        self.search_repository = search_repository
        self.roomsim_repository = roomsim_repository
        self.measurement_repository = measurement_repository
        self.objective_repository = objective_repository
        self.path = Path(search_repository.path)
        repositories = (roomsim_repository, measurement_repository)
        if any(Path(repository.path) != self.path for repository in repositories):
            raise ValueError('O60 repositories must share one native CAD database')
        if objective_repository is not None and Path(objective_repository.path) != self.path:
            raise ValueError('O60 objective repository must share one native CAD database')
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

    @staticmethod
    def _plan_linked(
        plans,
        *,
        candidate_id: str,
        measurement_id: str,
        candidate_set_sha256: str,
    ) -> bool:
        return any(
            plan.status == 'measured'
            and plan.candidate_id == candidate_id
            and plan.candidate_set_sha256 == candidate_set_sha256
            and measurement_id in plan.measurement_ids
            for plan in plans
        )

    @staticmethod
    def _measurement_plan_for_id(plans, measurement_id: str, candidate_set_sha256: str):
        return next(
            (
                plan
                for plan in plans
                if plan.status == 'measured'
                and plan.candidate_set_sha256 == candidate_set_sha256
                and measurement_id in plan.measurement_ids
            ),
            None,
        )

    def _measurement_response(self, measurement_id: str) -> FrequencyResponse:
        dataset = self.measurement_repository.dataset_for_measurement(measurement_id)
        if dataset is None:
            raise ValueError(f'validation measurement has no frequency response: {measurement_id}')
        return FrequencyResponse(
            frequency_hz=dataset.frequency_hz,
            level_db=dataset.level_db,
        )

    def _candidate_positions(self, spec, candidate_ids: set[str], candidate_set_sha256: str):
        remaining = set(candidate_ids)
        found = {}
        offset = 0
        page_limit = min(1000, spec.candidate_limit)
        while remaining:
            page = generate_cad_candidates(
                self.search_repository.scene_repository,
                spec,
                offset=offset,
                limit=page_limit,
            )
            if page.candidate_set_sha256 != candidate_set_sha256:
                raise ValueError('validation candidate-set hash does not match regenerated SearchSpec')
            for candidate in page.candidates:
                if candidate.candidate_id in remaining:
                    found[candidate.candidate_id] = candidate.positions
                    remaining.remove(candidate.candidate_id)
            offset += len(page.candidates)
            if not page.candidates or offset >= page.feasible_candidate_count:
                break
        if remaining:
            raise ValueError(f'validation references candidates outside SearchSpec: {sorted(remaining)}')
        return found

    @staticmethod
    def _placement_distance(left: dict, right: dict) -> float:
        if set(left) != set(right):
            raise ValueError('sensitivity candidates do not share the same moved entities')
        squared = 0.0
        for entity_id in sorted(left):
            if set(left[entity_id]) != {'x_m', 'y_m', 'z_m'} or set(right[entity_id]) != {
                'x_m', 'y_m', 'z_m'
            }:
                raise ValueError('candidate position payload is invalid')
            for axis in ('x_m', 'y_m', 'z_m'):
                delta = float(right[entity_id][axis]) - float(left[entity_id][axis])
                squared += delta * delta
        return sqrt(squared)

    def _validate_objective_samples(self, record: CadModelValidationRecord) -> None:
        if not record.objective_samples:
            return
        repository = self.objective_repository
        if repository is None:
            raise ValueError('full O60 validation requires CadObjectiveRepository')

        for sample in record.objective_samples:
            predicted = repository.get_evaluation(sample.predicted_evaluation_id)
            measured = repository.get_evaluation(sample.measured_evaluation_id)
            if predicted is None or measured is None:
                raise ValueError('objective validation references an unknown evaluation')
            for evaluation, expected_class, expected_value in (
                (predicted, 'predicted', sample.predicted_value),
                (measured, 'measured', sample.measured_value),
            ):
                if (
                    evaluation.document_id != record.document_id
                    or evaluation.search_spec_id != record.search_spec_id
                    or evaluation.search_spec_sha256 != record.search_spec_sha256
                    or evaluation.candidate_id != sample.candidate_id
                ):
                    raise ValueError('objective validation evaluation authority mismatch')
                evidence_classes = {ref.evidence_class for ref in evaluation.input_refs}
                if expected_class not in evidence_classes:
                    raise ValueError(
                        f'objective validation {expected_class} evaluation evidence mismatch'
                    )
                try:
                    metric = evaluation.vector.metric(sample.objective_id)
                except KeyError as exc:
                    raise ValueError('objective validation metric is missing from evaluation') from exc
                if metric.unit != sample.unit or abs(float(metric.value) - float(expected_value)) > 1e-12:
                    raise ValueError('objective validation metric snapshot mismatch')

    def _validate_sensitivity(
        self,
        record: CadModelValidationRecord,
        spec,
    ) -> None:
        if not record.sensitivity_checks:
            return
        sample_map = {
            (sample.candidate_id, sample.objective_id): sample
            for sample in record.objective_samples
        }
        candidate_ids = {
            candidate_id
            for check in record.sensitivity_checks
            for candidate_id in (check.candidate_a_id, check.candidate_b_id)
        }
        positions = self._candidate_positions(spec, candidate_ids, record.candidate_set_sha256)
        for check in record.sensitivity_checks:
            left = sample_map.get((check.candidate_a_id, check.objective_id))
            right = sample_map.get((check.candidate_b_id, check.objective_id))
            if left is None or right is None or left.split != 'holdout' or right.split != 'holdout':
                raise ValueError('sensitivity check requires holdout objective samples for both candidates')
            if left.unit != check.unit or right.unit != check.unit:
                raise ValueError('sensitivity objective unit mismatch')
            distance = self._placement_distance(
                positions[check.candidate_a_id],
                positions[check.candidate_b_id],
            )
            rebuilt = build_sensitivity_check(
                objective_id=check.objective_id,
                unit=check.unit,
                candidate_a_id=check.candidate_a_id,
                candidate_b_id=check.candidate_b_id,
                placement_delta_m=distance,
                predicted_a=left.predicted_value,
                predicted_b=right.predicted_value,
                measured_a=left.measured_value,
                measured_b=right.measured_value,
                max_observed_sensitivity_per_m=check.max_observed_sensitivity_per_m,
                max_model_error_per_m=check.max_model_error_per_m,
            )
            if rebuilt != check:
                raise ValueError('sensitivity check does not match candidate/objective evidence')

    def _validate_repeatability_and_separation(
        self,
        record: CadModelValidationRecord,
        plans,
    ) -> None:
        for check in record.repeatability_checks:
            measurements = []
            for measurement_id in check.measurement_ids:
                measurement = self.measurement_repository.get_measurement(measurement_id)
                if (
                    measurement is None
                    or measurement.evidence_type != 'measured'
                    or measurement.document_id != record.document_id
                    or measurement.scene_revision_id != check.scene_revision_id
                ):
                    raise ValueError('repeatability evidence binding mismatch')
                plan = self._measurement_plan_for_id(
                    plans,
                    measurement_id,
                    record.candidate_set_sha256,
                )
                if plan is None or plan.applied_scene_revision_id != check.scene_revision_id:
                    raise ValueError('repeatability measurement is not linked to an exact Measurement Plan')
                measurements.append((measurement_id, self._measurement_response(measurement_id)))
            rebuilt = build_repeatability_check(
                scene_revision_id=check.scene_revision_id,
                measurements=tuple(measurements),
                low_hz=check.requested_band_hz[0],
                high_hz=check.requested_band_hz[1],
                reference_band_hz=check.reference_band_hz,
            )
            if rebuilt != check:
                raise ValueError('repeatability check does not match immutable measurement evidence')

        for check in record.separation_checks:
            for candidate_id, measurement_id in (
                (check.candidate_a_id, check.measurement_a_id),
                (check.candidate_b_id, check.measurement_b_id),
            ):
                measurement = self.measurement_repository.get_measurement(measurement_id)
                if (
                    measurement is None
                    or measurement.evidence_type != 'measured'
                    or measurement.document_id != record.document_id
                ):
                    raise ValueError('candidate separation measurement binding mismatch')
                if not self._plan_linked(
                    plans,
                    candidate_id=candidate_id,
                    measurement_id=measurement_id,
                    candidate_set_sha256=record.candidate_set_sha256,
                ):
                    raise ValueError('candidate separation measurement is not linked to candidate plan')
            rebuilt = build_candidate_separation_check(
                candidate_a_id=check.candidate_a_id,
                candidate_b_id=check.candidate_b_id,
                measurement_a_id=check.measurement_a_id,
                measurement_b_id=check.measurement_b_id,
                response_a=self._measurement_response(check.measurement_a_id),
                response_b=self._measurement_response(check.measurement_b_id),
                low_hz=check.requested_band_hz[0],
                high_hz=check.requested_band_hz[1],
                repeatability_floor_db=check.repeatability_floor_db,
                min_repeatability_multiple=check.min_repeatability_multiple,
            )
            if rebuilt != check:
                raise ValueError('candidate separation check does not match measurement evidence')

    def save(self, record: CadModelValidationRecord) -> None:
        if not isinstance(record, CadModelValidationRecord):
            raise TypeError('record must be CadModelValidationRecord')
        record = CadModelValidationRecord.model_validate(record.model_dump(mode='python'))
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
            if not self._plan_linked(
                plans,
                candidate_id=pair.candidate_id,
                measurement_id=pair.measurement_id,
                candidate_set_sha256=record.candidate_set_sha256,
            ):
                raise ValueError('validation measurement is not linked to the candidate Measurement Plan')

        self._validate_objective_samples(record)
        self._validate_sensitivity(record, spec)
        self._validate_repeatability_and_separation(record, plans)

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
