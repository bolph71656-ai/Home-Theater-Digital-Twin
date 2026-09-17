from __future__ import annotations

from itertools import combinations
from math import isfinite, sqrt
from typing import Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .comparison import ComparisonError, FrequencyResponse, compare_frequency_responses


OBJECTIVE_ALGORITHM_VERSION = 'objective-vector-1'


class ObjectiveError(ValueError):
    pass


class ResponseObjectiveSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    low_hz: float = Field(gt=0.0)
    high_hz: float = Field(gt=0.0)
    reference_band_hz: tuple[float, float] | None = None
    excluded_bands: tuple[tuple[float, float], ...] = ()

    @model_validator(mode='after')
    def valid_bands(self) -> 'ResponseObjectiveSpec':
        if not isfinite(self.low_hz) or not isfinite(self.high_hz):
            raise ValueError('objective response band must be finite')
        if self.high_hz <= self.low_hz:
            raise ValueError('objective response high_hz must be greater than low_hz')
        if self.reference_band_hz is not None:
            low, high = self.reference_band_hz
            if not all(isfinite(value) and value > 0.0 for value in (low, high)) or high <= low:
                raise ValueError('reference band must be finite, positive and ordered')
        for low, high in self.excluded_bands:
            if not all(isfinite(value) and value > 0.0 for value in (low, high)) or high < low:
                raise ValueError('excluded bands must be finite, positive and ordered')
        return self


class ObjectiveMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective_id: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    direction: Literal['minimize'] = 'minimize'

    @model_validator(mode='after')
    def finite_value(self) -> 'ObjectiveMetric':
        if not isfinite(float(self.value)):
            raise ValueError('objective metric value must be finite')
        return self


class ObjectiveVector(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    metrics: tuple[ObjectiveMetric, ...] = Field(min_length=1)
    algorithm_version: Literal['objective-vector-1'] = OBJECTIVE_ALGORITHM_VERSION

    @model_validator(mode='after')
    def unique_objectives(self) -> 'ObjectiveVector':
        ids = [metric.objective_id for metric in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError('objective ids must be unique within a vector')
        return self

    def metric(self, objective_id: str) -> ObjectiveMetric:
        for metric in self.metrics:
            if metric.objective_id == objective_id:
                return metric
        raise KeyError(objective_id)


def _comparison(
    response: FrequencyResponse,
    reference: FrequencyResponse,
    spec: ResponseObjectiveSpec,
):
    try:
        return compare_frequency_responses(
            response,
            reference,
            spec.low_hz,
            spec.high_hz,
            reference_band_hz=spec.reference_band_hz,
            excluded_bands=spec.excluded_bands,
        )
    except ComparisonError as exc:
        raise ObjectiveError(str(exc)) from exc


def target_response_objectives(
    candidate_id: str,
    response: FrequencyResponse,
    target: FrequencyResponse,
    spec: ResponseObjectiveSpec,
    *,
    prefix: str = 'response',
) -> ObjectiveVector:
    result = _comparison(response, target, spec)
    if result.rms_difference_db is None or not result.difference_db:
        raise ObjectiveError('target response objective requires at least two valid frequency points')

    peak_excess = max(0.0, max(result.difference_db))
    dip_deficit = max(0.0, -min(result.difference_db))
    metrics: list[ObjectiveMetric] = [
        ObjectiveMetric(
            objective_id=f'{prefix}.rms_difference_db',
            value=result.rms_difference_db,
            unit='dB',
        ),
        ObjectiveMetric(
            objective_id=f'{prefix}.peak_excess_db',
            value=peak_excess,
            unit='dB',
        ),
        ObjectiveMetric(
            objective_id=f'{prefix}.dip_deficit_db',
            value=dip_deficit,
            unit='dB',
        ),
    ]
    if spec.reference_band_hz is not None:
        if result.shape_rms_db is None:
            raise ObjectiveError('shape objective requires at least two valid reference-band points')
        metrics.append(ObjectiveMetric(
            objective_id=f'{prefix}.shape_rms_db',
            value=result.shape_rms_db,
            unit='dB',
        ))
    return ObjectiveVector(candidate_id=candidate_id, metrics=tuple(metrics))


def pair_response_objectives(
    candidate_id: str,
    a: FrequencyResponse,
    b: FrequencyResponse,
    spec: ResponseObjectiveSpec,
    *,
    prefix: str = 'pair',
) -> ObjectiveVector:
    result = _comparison(a, b, spec)
    if result.rms_difference_db is None:
        raise ObjectiveError('pair response objective requires at least two valid frequency points')

    metrics: list[ObjectiveMetric] = [
        ObjectiveMetric(
            objective_id=f'{prefix}.rms_difference_db',
            value=result.rms_difference_db,
            unit='dB',
        ),
    ]
    if spec.reference_band_hz is not None:
        if result.shape_rms_db is None:
            raise ObjectiveError('pair shape objective requires at least two valid reference-band points')
        metrics.append(ObjectiveMetric(
            objective_id=f'{prefix}.shape_rms_db',
            value=result.shape_rms_db,
            unit='dB',
        ))
    return ObjectiveVector(candidate_id=candidate_id, metrics=tuple(metrics))


def seat_pairwise_objectives(
    candidate_id: str,
    responses: Sequence[FrequencyResponse],
    spec: ResponseObjectiveSpec,
    *,
    prefix: str = 'seat',
) -> ObjectiveVector:
    if len(responses) < 2:
        raise ObjectiveError('seat spread objective requires at least two responses')

    pair_values: list[float] = []
    for a, b in combinations(responses, 2):
        result = _comparison(a, b, spec)
        value = result.shape_rms_db if spec.reference_band_hz is not None else result.rms_difference_db
        if value is None:
            raise ObjectiveError('seat spread objective requires at least two valid points per pair')
        pair_values.append(float(value))

    rms = sqrt(sum(value * value for value in pair_values) / len(pair_values))
    return ObjectiveVector(
        candidate_id=candidate_id,
        metrics=(
            ObjectiveMetric(
                objective_id=f'{prefix}.pairwise_max_db',
                value=max(pair_values),
                unit='dB',
            ),
            ObjectiveMetric(
                objective_id=f'{prefix}.pairwise_rms_db',
                value=rms,
                unit='dB',
            ),
        ),
    )


def _xyz(position: Mapping[str, float]) -> tuple[float, float, float]:
    try:
        values = (
            float(position['x_m']),
            float(position['y_m']),
            float(position['z_m']),
        )
    except KeyError as exc:
        raise ObjectiveError('movement position requires x_m/y_m/z_m') from exc
    if not all(isfinite(value) for value in values):
        raise ObjectiveError('movement positions must be finite')
    return values


def movement_objectives(
    candidate_id: str,
    baseline_positions: Mapping[str, Mapping[str, float]],
    candidate_positions: Mapping[str, Mapping[str, float]],
    *,
    prefix: str = 'movement',
) -> ObjectiveVector:
    if not candidate_positions:
        raise ObjectiveError('movement objective requires at least one moved entity')

    distances: list[float] = []
    for entity_id in sorted(candidate_positions):
        if entity_id not in baseline_positions:
            raise ObjectiveError(f'missing movement baseline for entity: {entity_id}')
        before = _xyz(baseline_positions[entity_id])
        after = _xyz(candidate_positions[entity_id])
        distances.append(sqrt(sum((b - a) ** 2 for a, b in zip(before, after, strict=True))))

    return ObjectiveVector(
        candidate_id=candidate_id,
        metrics=(
            ObjectiveMetric(
                objective_id=f'{prefix}.total_m',
                value=sum(distances),
                unit='m',
            ),
            ObjectiveMetric(
                objective_id=f'{prefix}.max_m',
                value=max(distances),
                unit='m',
            ),
        ),
    )


def merge_objective_vectors(candidate_id: str, *vectors: ObjectiveVector) -> ObjectiveVector:
    if not vectors:
        raise ObjectiveError('at least one objective vector is required')

    merged: list[ObjectiveMetric] = []
    seen: set[str] = set()
    for vector in vectors:
        if vector.candidate_id != candidate_id:
            raise ObjectiveError('cannot merge objective vectors for different candidates')
        for metric in vector.metrics:
            if metric.objective_id in seen:
                raise ObjectiveError(f'duplicate objective while merging: {metric.objective_id}')
            seen.add(metric.objective_id)
            merged.append(metric)
    return ObjectiveVector(candidate_id=candidate_id, metrics=tuple(merged))
