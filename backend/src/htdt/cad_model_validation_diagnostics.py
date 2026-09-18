from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
from math import isfinite, sqrt
from typing import Any, Literal, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_model_validation import CadModelValidationRecord
from .cad_objective_models import CadObjectiveEvaluation


VALIDATION_DIAGNOSTICS_ALGORITHM_VERSION = 'model-validation-diagnostics-1'
PLACEMENT_DISTANCE_ALGORITHM_VERSION = 'candidate-position-l2-1'


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode('utf-8')).hexdigest()


class CadObjectiveValidationThreshold(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    min_trend_agreement: float = Field(ge=0.0, le=1.0)
    trend_tolerance: float = Field(ge=0.0)
    max_sensitivity_per_m: float = Field(gt=0.0)
    repeatability_factor: float = Field(gt=0.0)


class CadDiagnosticEvaluationRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluation_id: str = Field(min_length=1)
    evaluation_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class CadObjectiveDiagnosticSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    predicted: CadDiagnosticEvaluationRef
    measured: tuple[CadDiagnosticEvaluationRef, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_measured(self) -> 'CadObjectiveDiagnosticSource':
        ids = [item.evaluation_id for item in self.measured]
        if len(ids) != len(set(ids)):
            raise ValueError('measured diagnostic evaluation ids must be unique')
        return self


class CadObjectiveTrendDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    comparable_pairs: int = Field(ge=0)
    concordant_pairs: int = Field(ge=0)
    discordant_pairs: int = Field(ge=0)
    tied_pairs: int = Field(ge=0)
    agreement: float | None = Field(default=None, ge=0.0, le=1.0)
    min_agreement: float = Field(ge=0.0, le=1.0)
    tolerance: float = Field(ge=0.0)
    status: Literal['pass', 'fail', 'insufficient']


class CadObjectiveSensitivityDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    candidate_pair_count: int = Field(ge=0)
    sensitivity_radius_m: float = Field(gt=0.0)
    max_predicted_sensitivity_per_m: float | None = Field(default=None, ge=0.0)
    max_measured_sensitivity_per_m: float | None = Field(default=None, ge=0.0)
    max_allowed_sensitivity_per_m: float = Field(gt=0.0)
    status: Literal['pass', 'fail', 'insufficient']


class CadObjectiveRepeatabilityDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    candidates_with_required_repeats: int = Field(ge=0)
    min_repeat_measurements: int = Field(ge=2)
    max_repeatability_rms: float | None = Field(default=None, ge=0.0)
    min_between_candidate_difference: float | None = Field(default=None, ge=0.0)
    required_separation_factor: float = Field(gt=0.0)
    status: Literal['pass', 'fail', 'insufficient']


class CadModelValidationAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessment_id: str = Field(min_length=1)
    validation_id: str = Field(min_length=1)
    validation_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    document_id: str = Field(min_length=1)
    search_spec_id: str = Field(min_length=1)
    search_spec_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_set_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    sources: tuple[CadObjectiveDiagnosticSource, ...] = Field(min_length=1)
    thresholds: tuple[CadObjectiveValidationThreshold, ...] = Field(min_length=1)
    min_holdout_candidates: int = Field(ge=2)
    min_repeat_measurements: int = Field(ge=2)
    sensitivity_radius_m: float = Field(gt=0.0)
    placement_distance_algorithm: Literal['candidate-position-l2-1'] = PLACEMENT_DISTANCE_ALGORITHM_VERSION
    trend: tuple[CadObjectiveTrendDiagnostic, ...] = Field(min_length=1)
    sensitivity: tuple[CadObjectiveSensitivityDiagnostic, ...] = Field(min_length=1)
    repeatability: tuple[CadObjectiveRepeatabilityDiagnostic, ...] = Field(min_length=1)
    o70_gate: Literal['eligible', 'disabled']
    gate_reasons: tuple[str, ...]
    algorithm_version: Literal['model-validation-diagnostics-1'] = VALIDATION_DIAGNOSTICS_ALGORITHM_VERSION
    created_at_utc: str = Field(min_length=1)
    assessment_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_identity(self) -> 'CadModelValidationAssessment':
        objective_ids = [threshold.objective_id for threshold in self.thresholds]
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError('diagnostic objective thresholds must be unique')
        for collection in (self.trend, self.sensitivity, self.repeatability):
            ids = [item.objective_id for item in collection]
            if tuple(ids) != tuple(objective_ids):
                raise ValueError('diagnostic objective ordering must match thresholds')
        if self.o70_gate == 'eligible':
            if self.gate_reasons:
                raise ValueError('eligible O70 gate cannot contain stop reasons')
            if any(
                item.status != 'pass'
                for collection in (self.trend, self.sensitivity, self.repeatability)
                for item in collection
            ):
                raise ValueError('eligible O70 gate requires every diagnostic to pass')
        elif not self.gate_reasons:
            raise ValueError('disabled O70 gate requires at least one stop reason')
        if self.assessment_sha256 != _sha256(self.identity_payload()):
            raise ValueError('model validation assessment identity hash mismatch')
        return self

    def identity_payload(self) -> dict[str, Any]:
        return {
            'validation_id': self.validation_id,
            'validation_sha256': self.validation_sha256,
            'document_id': self.document_id,
            'search_spec_id': self.search_spec_id,
            'search_spec_sha256': self.search_spec_sha256,
            'candidate_set_sha256': self.candidate_set_sha256,
            'model_id': self.model_id,
            'model_version': self.model_version,
            'sources': [item.model_dump(mode='json') for item in self.sources],
            'thresholds': [item.model_dump(mode='json') for item in self.thresholds],
            'min_holdout_candidates': self.min_holdout_candidates,
            'min_repeat_measurements': self.min_repeat_measurements,
            'sensitivity_radius_m': self.sensitivity_radius_m,
            'placement_distance_algorithm': self.placement_distance_algorithm,
            'trend': [item.model_dump(mode='json') for item in self.trend],
            'sensitivity': [item.model_dump(mode='json') for item in self.sensitivity],
            'repeatability': [item.model_dump(mode='json') for item in self.repeatability],
            'o70_gate': self.o70_gate,
            'gate_reasons': list(self.gate_reasons),
            'algorithm_version': self.algorithm_version,
        }


def _metric(evaluation: CadObjectiveEvaluation, objective_id: str, unit: str) -> float:
    try:
        metric = evaluation.vector.metric(objective_id)
    except KeyError as exc:
        raise ValueError(
            f'evaluation {evaluation.evaluation_id} is missing objective {objective_id}'
        ) from exc
    if metric.unit != unit:
        raise ValueError(
            f'evaluation {evaluation.evaluation_id} objective unit mismatch for {objective_id}'
        )
    value = float(metric.value)
    if not isfinite(value):
        raise ValueError('diagnostic objective values must be finite')
    return value


def _validate_evaluation_authority(
    validation: CadModelValidationRecord,
    evaluation: CadObjectiveEvaluation,
) -> None:
    if (
        evaluation.document_id != validation.document_id
        or evaluation.search_spec_id != validation.search_spec_id
        or evaluation.search_spec_sha256 != validation.search_spec_sha256
    ):
        raise ValueError('diagnostic evaluation SearchSpec authority mismatch')


def _placement_distance(
    a: Mapping[str, Mapping[str, float]],
    b: Mapping[str, Mapping[str, float]],
) -> float:
    if set(a) != set(b) or not a:
        raise ValueError('diagnostic candidate positions must contain the same non-empty entity set')
    squared = 0.0
    for entity_id in sorted(a):
        for axis in ('x_m', 'y_m', 'z_m'):
            if axis not in a[entity_id] or axis not in b[entity_id]:
                raise ValueError('diagnostic candidate position requires x_m/y_m/z_m')
            first = float(a[entity_id][axis])
            second = float(b[entity_id][axis])
            if not isfinite(first) or not isfinite(second):
                raise ValueError('diagnostic candidate positions must be finite')
            squared += (first - second) ** 2
    return sqrt(squared)


def _sign(value: float, tolerance: float) -> int:
    if abs(value) <= tolerance:
        return 0
    return 1 if value > 0.0 else -1


def build_model_validation_assessment(
    validation: CadModelValidationRecord,
    *,
    predicted_evaluations: tuple[CadObjectiveEvaluation, ...],
    measured_evaluations: tuple[CadObjectiveEvaluation, ...],
    candidate_positions: Mapping[str, Mapping[str, Mapping[str, float]]],
    thresholds: tuple[CadObjectiveValidationThreshold, ...],
    min_holdout_candidates: int = 3,
    min_repeat_measurements: int = 2,
    sensitivity_radius_m: float = 0.20,
) -> CadModelValidationAssessment:
    if min_holdout_candidates < 2:
        raise ValueError('min_holdout_candidates must be at least 2')
    if min_repeat_measurements < 2:
        raise ValueError('min_repeat_measurements must be at least 2')
    if not isfinite(sensitivity_radius_m) or sensitivity_radius_m <= 0.0:
        raise ValueError('sensitivity_radius_m must be finite and positive')
    if not thresholds:
        raise ValueError('at least one objective diagnostic threshold is required')

    threshold_ids = [threshold.objective_id for threshold in thresholds]
    if len(threshold_ids) != len(set(threshold_ids)):
        raise ValueError('objective diagnostic thresholds must be unique')

    holdout_candidates = tuple(sorted({
        pair.candidate_id for pair in validation.pairs if pair.split == 'holdout'
    }))
    holdout_set = set(holdout_candidates)
    if not holdout_candidates:
        raise ValueError('diagnostic assessment requires holdout candidates')

    predicted_by_candidate: dict[str, CadObjectiveEvaluation] = {}
    for evaluation in predicted_evaluations:
        _validate_evaluation_authority(validation, evaluation)
        if evaluation.candidate_id not in holdout_set:
            raise ValueError('predicted diagnostic evaluation is not a holdout candidate')
        classes = {ref.evidence_class for ref in evaluation.input_refs}
        if 'predicted' not in classes or 'measured' in classes:
            raise ValueError('predicted diagnostic evaluation must contain predicted but not measured evidence')
        if evaluation.candidate_id in predicted_by_candidate:
            raise ValueError('exactly one predicted diagnostic evaluation is required per holdout candidate')
        predicted_by_candidate[evaluation.candidate_id] = evaluation

    measured_by_candidate: dict[str, list[CadObjectiveEvaluation]] = {
        candidate_id: [] for candidate_id in holdout_candidates
    }
    for evaluation in measured_evaluations:
        _validate_evaluation_authority(validation, evaluation)
        if evaluation.candidate_id not in holdout_set:
            raise ValueError('measured diagnostic evaluation is not a holdout candidate')
        classes = {ref.evidence_class for ref in evaluation.input_refs}
        if 'measured' not in classes or 'predicted' in classes:
            raise ValueError('measured diagnostic evaluation must contain measured but not predicted evidence')
        measured_by_candidate[evaluation.candidate_id].append(evaluation)

    missing_predicted = [
        candidate_id for candidate_id in holdout_candidates
        if candidate_id not in predicted_by_candidate
    ]
    missing_measured = [
        candidate_id for candidate_id in holdout_candidates
        if not measured_by_candidate[candidate_id]
    ]
    if missing_predicted:
        raise ValueError(f'missing predicted evaluation for holdout candidates: {missing_predicted}')
    if missing_measured:
        raise ValueError(f'missing measured evaluation for holdout candidates: {missing_measured}')
    if set(candidate_positions) != holdout_set:
        raise ValueError('candidate position set must exactly match holdout candidates')

    sources: list[CadObjectiveDiagnosticSource] = []
    for candidate_id in holdout_candidates:
        predicted = predicted_by_candidate[candidate_id]
        measured = tuple(sorted(
            measured_by_candidate[candidate_id],
            key=lambda item: (item.created_at_utc, item.evaluation_id),
        ))
        sources.append(CadObjectiveDiagnosticSource(
            candidate_id=candidate_id,
            predicted=CadDiagnosticEvaluationRef(
                evaluation_id=predicted.evaluation_id,
                evaluation_sha256=predicted.evaluation_sha256,
            ),
            measured=tuple(
                CadDiagnosticEvaluationRef(
                    evaluation_id=item.evaluation_id,
                    evaluation_sha256=item.evaluation_sha256,
                )
                for item in measured
            ),
        ))

    trend_diagnostics: list[CadObjectiveTrendDiagnostic] = []
    sensitivity_diagnostics: list[CadObjectiveSensitivityDiagnostic] = []
    repeatability_diagnostics: list[CadObjectiveRepeatabilityDiagnostic] = []

    for threshold in thresholds:
        predicted_values = {
            candidate_id: _metric(
                predicted_by_candidate[candidate_id],
                threshold.objective_id,
                threshold.unit,
            )
            for candidate_id in holdout_candidates
        }
        measured_values = {
            candidate_id: tuple(
                _metric(item, threshold.objective_id, threshold.unit)
                for item in measured_by_candidate[candidate_id]
            )
            for candidate_id in holdout_candidates
        }
        measured_means = {
            candidate_id: sum(values) / len(values)
            for candidate_id, values in measured_values.items()
        }

        concordant = 0
        discordant = 0
        tied = 0
        for first, second in combinations(holdout_candidates, 2):
            predicted_sign = _sign(
                predicted_values[first] - predicted_values[second],
                threshold.trend_tolerance,
            )
            measured_sign = _sign(
                measured_means[first] - measured_means[second],
                threshold.trend_tolerance,
            )
            if predicted_sign == 0 or measured_sign == 0:
                tied += 1
            elif predicted_sign == measured_sign:
                concordant += 1
            else:
                discordant += 1
        comparable = concordant + discordant
        agreement = None if comparable == 0 else concordant / comparable
        if len(holdout_candidates) < min_holdout_candidates or agreement is None:
            trend_status = 'insufficient'
        elif agreement >= threshold.min_trend_agreement:
            trend_status = 'pass'
        else:
            trend_status = 'fail'
        trend_diagnostics.append(CadObjectiveTrendDiagnostic(
            objective_id=threshold.objective_id,
            unit=threshold.unit,
            candidate_count=len(holdout_candidates),
            comparable_pairs=comparable,
            concordant_pairs=concordant,
            discordant_pairs=discordant,
            tied_pairs=tied,
            agreement=agreement,
            min_agreement=threshold.min_trend_agreement,
            tolerance=threshold.trend_tolerance,
            status=trend_status,
        ))

        sensitivity_pairs = 0
        max_predicted_sensitivity: float | None = None
        max_measured_sensitivity: float | None = None
        for first, second in combinations(holdout_candidates, 2):
            distance = _placement_distance(
                candidate_positions[first],
                candidate_positions[second],
            )
            if distance <= 0.0 or distance > sensitivity_radius_m:
                continue
            sensitivity_pairs += 1
            predicted_slope = abs(predicted_values[first] - predicted_values[second]) / distance
            measured_slope = abs(measured_means[first] - measured_means[second]) / distance
            max_predicted_sensitivity = (
                predicted_slope
                if max_predicted_sensitivity is None
                else max(max_predicted_sensitivity, predicted_slope)
            )
            max_measured_sensitivity = (
                measured_slope
                if max_measured_sensitivity is None
                else max(max_measured_sensitivity, measured_slope)
            )
        if sensitivity_pairs == 0:
            sensitivity_status = 'insufficient'
        elif (
            max_predicted_sensitivity is not None
            and max_measured_sensitivity is not None
            and max(max_predicted_sensitivity, max_measured_sensitivity)
            <= threshold.max_sensitivity_per_m
        ):
            sensitivity_status = 'pass'
        else:
            sensitivity_status = 'fail'
        sensitivity_diagnostics.append(CadObjectiveSensitivityDiagnostic(
            objective_id=threshold.objective_id,
            unit=threshold.unit,
            candidate_pair_count=sensitivity_pairs,
            sensitivity_radius_m=sensitivity_radius_m,
            max_predicted_sensitivity_per_m=max_predicted_sensitivity,
            max_measured_sensitivity_per_m=max_measured_sensitivity,
            max_allowed_sensitivity_per_m=threshold.max_sensitivity_per_m,
            status=sensitivity_status,
        ))

        repeatability_values: list[float] = []
        with_required_repeats = 0
        for candidate_id in holdout_candidates:
            values = measured_values[candidate_id]
            mean = measured_means[candidate_id]
            if len(values) >= min_repeat_measurements:
                with_required_repeats += 1
            repeatability_values.append(
                sqrt(sum((value - mean) ** 2 for value in values) / len(values))
            )
        max_repeatability = max(repeatability_values) if repeatability_values else None
        between_differences = [
            abs(measured_means[first] - measured_means[second])
            for first, second in combinations(holdout_candidates, 2)
        ]
        min_between = min(between_differences) if between_differences else None
        if (
            len(holdout_candidates) < min_holdout_candidates
            or with_required_repeats != len(holdout_candidates)
            or max_repeatability is None
            or min_between is None
        ):
            repeatability_status = 'insufficient'
        elif min_between > threshold.repeatability_factor * max_repeatability:
            repeatability_status = 'pass'
        else:
            repeatability_status = 'fail'
        repeatability_diagnostics.append(CadObjectiveRepeatabilityDiagnostic(
            objective_id=threshold.objective_id,
            unit=threshold.unit,
            candidate_count=len(holdout_candidates),
            candidates_with_required_repeats=with_required_repeats,
            min_repeat_measurements=min_repeat_measurements,
            max_repeatability_rms=max_repeatability,
            min_between_candidate_difference=min_between,
            required_separation_factor=threshold.repeatability_factor,
            status=repeatability_status,
        ))

    gate_reasons: list[str] = []
    if validation.residual_gate != 'pass':
        gate_reasons.append(f'residual gate is {validation.residual_gate}, not pass')
    if len(holdout_candidates) < min_holdout_candidates:
        gate_reasons.append(
            f'holdout candidates {len(holdout_candidates)} < required {min_holdout_candidates}'
        )
    for collection_name, diagnostics in (
        ('trend', trend_diagnostics),
        ('sensitivity', sensitivity_diagnostics),
        ('repeatability', repeatability_diagnostics),
    ):
        for diagnostic in diagnostics:
            if diagnostic.status != 'pass':
                gate_reasons.append(
                    f'{collection_name} {diagnostic.objective_id} is {diagnostic.status}'
                )

    payload = {
        'validation_id': validation.validation_id,
        'validation_sha256': validation.validation_sha256,
        'document_id': validation.document_id,
        'search_spec_id': validation.search_spec_id,
        'search_spec_sha256': validation.search_spec_sha256,
        'candidate_set_sha256': validation.candidate_set_sha256,
        'model_id': validation.model_id,
        'model_version': validation.model_version,
        'sources': tuple(sources),
        'thresholds': thresholds,
        'min_holdout_candidates': min_holdout_candidates,
        'min_repeat_measurements': min_repeat_measurements,
        'sensitivity_radius_m': float(sensitivity_radius_m),
        'placement_distance_algorithm': PLACEMENT_DISTANCE_ALGORITHM_VERSION,
        'trend': tuple(trend_diagnostics),
        'sensitivity': tuple(sensitivity_diagnostics),
        'repeatability': tuple(repeatability_diagnostics),
        'o70_gate': 'eligible' if not gate_reasons else 'disabled',
        'gate_reasons': tuple(gate_reasons),
        'algorithm_version': VALIDATION_DIAGNOSTICS_ALGORITHM_VERSION,
    }
    provisional = CadModelValidationAssessment.model_construct(
        assessment_id=str(uuid4()),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        assessment_sha256='0' * 64,
        **payload,
    )
    return CadModelValidationAssessment(
        **provisional.model_dump(exclude={'assessment_sha256'}),
        assessment_sha256=_sha256(provisional.identity_payload()),
    )
