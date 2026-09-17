from __future__ import annotations

from math import sqrt

import pytest

from htdt.comparison import FrequencyResponse
from htdt.optimization_objectives import (
    ObjectiveError,
    ObjectiveMetric,
    ObjectiveVector,
    ResponseObjectiveSpec,
    merge_objective_vectors,
    movement_objectives,
    pair_response_objectives,
    seat_pairwise_objectives,
    target_response_objectives,
)
from htdt.pareto import ParetoError, dominates, pareto_front


def response(levels: tuple[float, ...]) -> FrequencyResponse:
    return FrequencyResponse(
        frequency_hz=(20.0, 40.0, 80.0, 160.0),
        level_db=levels,
    )


def test_target_response_keeps_level_shape_peak_and_dip_independent() -> None:
    spec = ResponseObjectiveSpec(
        low_hz=20.0,
        high_hz=160.0,
        reference_band_hz=(20.0, 160.0),
    )
    vector = target_response_objectives(
        'candidate-a',
        response((3.0, 3.0, 3.0, 3.0)),
        response((0.0, 0.0, 0.0, 0.0)),
        spec,
    )

    assert vector.metric('response.rms_difference_db').value == pytest.approx(3.0)
    assert vector.metric('response.peak_excess_db').value == pytest.approx(3.0)
    assert vector.metric('response.dip_deficit_db').value == pytest.approx(0.0)
    assert vector.metric('response.shape_rms_db').value == pytest.approx(0.0)


def test_pair_and_seat_objectives_do_not_collapse_to_single_score() -> None:
    aligned = ResponseObjectiveSpec(
        low_hz=20.0,
        high_hz=160.0,
        reference_band_hz=(20.0, 160.0),
    )
    pair = pair_response_objectives(
        'candidate-a',
        response((1.0, 1.0, 1.0, 1.0)),
        response((-1.0, -1.0, -1.0, -1.0)),
        aligned,
        prefix='left_right',
    )
    assert pair.metric('left_right.rms_difference_db').value == pytest.approx(2.0)
    assert pair.metric('left_right.shape_rms_db').value == pytest.approx(0.0)

    unaligned = ResponseObjectiveSpec(low_hz=20.0, high_hz=160.0)
    seat = seat_pairwise_objectives(
        'candidate-a',
        (
            response((0.0, 0.0, 0.0, 0.0)),
            response((1.0, 1.0, 1.0, 1.0)),
            response((-1.0, -1.0, -1.0, -1.0)),
        ),
        unaligned,
    )
    assert seat.metric('seat.pairwise_max_db').value == pytest.approx(2.0)
    assert seat.metric('seat.pairwise_rms_db').value == pytest.approx(sqrt(2.0))


def test_movement_objectives_report_total_and_max_separately() -> None:
    vector = movement_objectives(
        'candidate-a',
        {
            'speaker': {'x_m': 0.0, 'y_m': 0.0, 'z_m': 0.0},
            'seat': {'x_m': 1.0, 'y_m': 1.0, 'z_m': 0.0},
        },
        {
            'speaker': {'x_m': 3.0, 'y_m': 4.0, 'z_m': 0.0},
            'seat': {'x_m': 1.0, 'y_m': 1.0, 'z_m': 12.0},
        },
    )
    assert vector.metric('movement.total_m').value == pytest.approx(17.0)
    assert vector.metric('movement.max_m').value == pytest.approx(12.0)


def test_merge_requires_same_candidate_and_unique_objective_ids() -> None:
    first = ObjectiveVector(
        candidate_id='a',
        metrics=(ObjectiveMetric(objective_id='x', value=1.0, unit='dB'),),
    )
    second = ObjectiveVector(
        candidate_id='a',
        metrics=(ObjectiveMetric(objective_id='y', value=2.0, unit='m'),),
    )
    merged = merge_objective_vectors('a', first, second)
    assert [metric.objective_id for metric in merged.metrics] == ['x', 'y']

    with pytest.raises(ObjectiveError):
        merge_objective_vectors('other', first)
    with pytest.raises(ObjectiveError):
        merge_objective_vectors('a', first, first)


def vector(candidate_id: str, x: float, y: float) -> ObjectiveVector:
    return ObjectiveVector(
        candidate_id=candidate_id,
        metrics=(
            ObjectiveMetric(objective_id='x', value=x, unit='u'),
            ObjectiveMetric(objective_id='y', value=y, unit='u'),
        ),
    )


def test_pareto_front_keeps_known_non_dominated_set_in_input_order() -> None:
    result = pareto_front((
        vector('a', 1.0, 4.0),
        vector('b', 2.0, 2.0),
        vector('c', 4.0, 1.0),
        vector('d', 3.0, 3.0),
        vector('e', 2.0, 2.0),
    ))

    assert result.non_dominated_candidate_ids == ('a', 'b', 'c', 'e')
    assert result.dominated_by['d'] == ('b', 'e')
    assert result.dominated_by['b'] == ()
    assert dominates((1.0, 1.0), (1.0, 2.0))
    assert not dominates((1.0, 1.0), (1.0, 1.0))


def test_pareto_rejects_missing_objective_or_duplicate_candidate() -> None:
    with pytest.raises(ParetoError):
        pareto_front((
            vector('a', 1.0, 2.0),
            ObjectiveVector(
                candidate_id='b',
                metrics=(ObjectiveMetric(objective_id='x', value=1.0, unit='u'),),
            ),
        ))

    with pytest.raises(ParetoError):
        pareto_front((vector('a', 1.0, 2.0), vector('a', 2.0, 1.0)))
