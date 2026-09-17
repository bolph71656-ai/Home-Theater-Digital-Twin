from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .optimization_objectives import ObjectiveVector


PARETO_ALGORITHM_VERSION = 'pareto-front-1'


class ParetoError(ValueError):
    pass


class ParetoResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    algorithm_version: Literal['pareto-front-1'] = PARETO_ALGORITHM_VERSION
    objective_ids: tuple[str, ...] = Field(min_length=1)
    non_dominated_candidate_ids: tuple[str, ...]
    dominated_by: dict[str, tuple[str, ...]]

    @model_validator(mode='after')
    def valid_candidate_partition(self) -> 'ParetoResult':
        if len(self.objective_ids) != len(set(self.objective_ids)):
            raise ValueError('Pareto objective ids must be unique')
        return self


def _metric_values(vector: ObjectiveVector, objective_ids: tuple[str, ...]) -> tuple[float, ...]:
    values: list[float] = []
    for objective_id in objective_ids:
        try:
            metric = vector.metric(objective_id)
        except KeyError as exc:
            raise ParetoError(
                f'candidate {vector.candidate_id} is missing objective {objective_id}'
            ) from exc
        if metric.direction != 'minimize':
            raise ParetoError(f'unsupported Pareto objective direction: {metric.direction}')
        values.append(float(metric.value))
    return tuple(values)


def dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    if len(a) != len(b) or not a:
        raise ParetoError('dominance comparison requires non-empty vectors of equal length')
    return all(left <= right for left, right in zip(a, b, strict=True)) and any(
        left < right for left, right in zip(a, b, strict=True)
    )


def pareto_front(
    vectors: Sequence[ObjectiveVector],
    objective_ids: Sequence[str] | None = None,
) -> ParetoResult:
    if not vectors:
        raise ParetoError('Pareto extraction requires at least one objective vector')

    candidate_ids = [vector.candidate_id for vector in vectors]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ParetoError('candidate ids must be unique for Pareto extraction')

    if objective_ids is None:
        selected = tuple(metric.objective_id for metric in vectors[0].metrics)
    else:
        selected = tuple(objective_ids)
    if not selected or len(selected) != len(set(selected)):
        raise ParetoError('Pareto objective ids must be non-empty and unique')

    values = {
        vector.candidate_id: _metric_values(vector, selected)
        for vector in vectors
    }
    dominated_by: dict[str, tuple[str, ...]] = {}
    non_dominated: list[str] = []
    for vector in vectors:
        dominators = tuple(
            other.candidate_id
            for other in vectors
            if other.candidate_id != vector.candidate_id
            and dominates(values[other.candidate_id], values[vector.candidate_id])
        )
        dominated_by[vector.candidate_id] = dominators
        if not dominators:
            non_dominated.append(vector.candidate_id)

    return ParetoResult(
        objective_ids=selected,
        non_dominated_candidate_ids=tuple(non_dominated),
        dominated_by=dominated_by,
    )
