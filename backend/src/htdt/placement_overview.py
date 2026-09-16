from __future__ import annotations

import math
from typing import Any

from .conditions import context_differences


PLACEMENT_OVERVIEW_VERSION = 'placement-overview-1'


def _point(payload: dict[str, Any] | None) -> tuple[float, float, float] | None:
    if not isinstance(payload, dict):
        return None
    try:
        values = (float(payload['x_m']), float(payload['y_m']), float(payload['z_m']))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    return values


def _distance(a: tuple[float, float, float] | None, b: tuple[float, float, float] | None) -> float | None:
    if a is None or b is None:
        return None
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def _speaker_positions(context_payload: dict[str, Any]) -> dict[str, tuple[float, float, float] | None]:
    result: dict[str, tuple[float, float, float] | None] = {}
    for speaker in context_payload.get('speakers', []):
        speaker_id = str(speaker.get('speaker_id', '')).strip()
        if speaker_id:
            result[speaker_id] = _point(speaker.get('position'))
    return result


def _movement_from_reference(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    reference_payload = reference['payload']
    candidate_payload = candidate['payload']
    reference_point = _point((reference_payload.get('measurement_point') or {}).get('position'))
    candidate_point = _point((candidate_payload.get('measurement_point') or {}).get('position'))
    ref_speakers = _speaker_positions(reference_payload)
    candidate_speakers = _speaker_positions(candidate_payload)
    all_ids = sorted(set(ref_speakers) | set(candidate_speakers))
    speaker_movements = []
    for speaker_id in all_ids:
        reference_position = ref_speakers.get(speaker_id)
        candidate_position = candidate_speakers.get(speaker_id)
        speaker_movements.append({
            'speaker_id': speaker_id,
            'reference_position_m': reference_position,
            'candidate_position_m': candidate_position,
            'distance_m': _distance(reference_position, candidate_position),
        })
    known_distances = [row['distance_m'] for row in speaker_movements if row['distance_m'] is not None]
    return {
        'measurement_point_distance_m': _distance(reference_point, candidate_point),
        'speaker_movements': speaker_movements,
        'max_known_speaker_movement_m': max(known_distances) if known_distances else None,
    }


def _measurement_point_identity(context_payload: dict[str, Any]) -> tuple[str | None, str | None]:
    measurement_point = context_payload.get('measurement_point') or {}
    point_id = measurement_point.get('point_id')
    label = measurement_point.get('label')
    return (str(point_id) if point_id is not None else None, str(label) if label is not None else None)


def _comparison_for_pair(comparisons: list[dict[str, Any]], reference_dataset_id: str, candidate_dataset_id: str) -> dict[str, Any] | None:
    if reference_dataset_id == candidate_dataset_id:
        return None
    for comparison in comparisons:
        a_id = comparison.get('dataset_a_id')
        b_id = comparison.get('dataset_b_id')
        if {a_id, b_id} != {reference_dataset_id, candidate_dataset_id}:
            continue
        result = comparison.get('result') or {}
        return {
            'id': comparison['id'],
            'created_at': comparison.get('created_at'),
            'reference_side': 'A' if a_id == reference_dataset_id else 'B',
            'candidate_side': 'B' if a_id == reference_dataset_id else 'A',
            'spec': comparison.get('spec') or {},
            'metrics_as_saved': {
                'mean_difference_db': result.get('mean_difference_db'),
                'rms_difference_db': result.get('rms_difference_db'),
                'level_offset_db': result.get('level_offset_db'),
                'shape_rms_db': result.get('shape_rms_db'),
                'valid_points': result.get('valid_points'),
                'total_grid_points': result.get('total_grid_points'),
                'algorithm_version': result.get('algorithm_version'),
            },
            'comparison_role': result.get('comparison_role'),
            'interpretation_warnings': result.get('interpretation_warnings') or [],
            'confounders': result.get('confounders') or [],
            'intended_changes': result.get('intended_changes') or [],
        }
    return None


def build_placement_overview(
    *,
    contexts: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    channel_role: str | None = None,
    measurement_point_id: str | None = None,
    reference_dataset_id: str | None = None,
) -> dict[str, Any]:
    contexts_by_id = {context['id']: context for context in contexts}
    filtered: list[dict[str, Any]] = []
    for measurement in measurements:
        context = contexts_by_id.get(measurement['context_id'])
        if context is None:
            continue
        point_id, point_label = _measurement_point_identity(context['payload'])
        if channel_role is not None and measurement['channel_role'] != channel_role:
            continue
        if measurement_point_id is not None and point_id != measurement_point_id:
            continue
        filtered.append({
            'measurement': measurement,
            'context': context,
            'point_id': point_id,
            'point_label': point_label,
        })

    reference_entry = None
    if reference_dataset_id is not None:
        reference_entry = next((entry for entry in filtered if entry['measurement']['dataset_id'] == reference_dataset_id), None)
        if reference_entry is None:
            raise ValueError('reference_dataset_id is not present in the filtered overview')

    rows: list[dict[str, Any]] = []
    for entry in filtered:
        measurement = entry['measurement']
        context = entry['context']
        movement = None
        differences: list[dict[str, Any]] = []
        saved_comparison = None
        if reference_entry is not None:
            movement = _movement_from_reference(reference_entry['context'], context)
            differences = context_differences(reference_entry['context']['payload'], context['payload'])
            saved_comparison = _comparison_for_pair(
                comparisons,
                reference_entry['measurement']['dataset_id'],
                measurement['dataset_id'],
            )
        rows.append({
            'dataset_id': measurement['dataset_id'],
            'measurement_id': measurement['id'],
            'context_id': context['id'],
            'context_revision_number': context['revision_number'],
            'channel_role': measurement['channel_role'],
            'evidence_type': measurement['evidence_type'],
            'quality_status': measurement['quality_status'],
            'quality_reasons': measurement.get('quality_reasons') or [],
            'repeat_group': measurement.get('repeat_group'),
            'captured_at': measurement.get('captured_at'),
            'imported_at': measurement.get('imported_at'),
            'measurement_point_id': entry['point_id'],
            'measurement_point_label': entry['point_label'],
            'measurement_point_position_m': _point((context['payload'].get('measurement_point') or {}).get('position')),
            'speaker_positions_m': _speaker_positions(context['payload']),
            'movement_from_reference': movement,
            'context_differences_from_reference': differences,
            'saved_comparison_to_reference': saved_comparison,
        })

    rows.sort(key=lambda row: (row['context_revision_number'], row['imported_at'] or '', row['dataset_id']))
    channel_roles = sorted({measurement['channel_role'] for measurement in measurements})
    point_ids = sorted({point_id for context in contexts for point_id, _ in [_measurement_point_identity(context['payload'])] if point_id is not None})
    return {
        'classification': 'measured_layout_overview_not_ranking',
        'algorithm_version': PLACEMENT_OVERVIEW_VERSION,
        'filters': {
            'channel_role': channel_role,
            'measurement_point_id': measurement_point_id,
            'reference_dataset_id': reference_dataset_id,
        },
        'available_channel_roles': channel_roles,
        'available_measurement_point_ids': point_ids,
        'row_count': len(rows),
        'rows': rows,
        'interpretation_notice': (
            'Rows are measurement/layout history. No row is ranked as best. Use quality, repeatability, context differences, '
            'and saved A/B comparisons before treating a layout change as an improvement.'
        ),
    }
