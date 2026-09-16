from __future__ import annotations

import pytest

from htdt.spatial_editor import ContextDraft, normalize_direction, snap_scalar


def source_context() -> dict:
    return {
        'id': 'ctx-1', 'revision_number': 7,
        'payload': {
            'room': {'width_m': 4.0, 'depth_m': 5.0, 'height_m': 2.4, 'geometry_kind': 'rectangular'},
            'speakers': [
                {'speaker_id': 'FL', 'role': 'front_left', 'position': {'x_m': 1.0, 'y_m': 1.0, 'z_m': 1.0}},
                {'speaker_id': 'FR', 'role': 'front_right', 'position': {'x_m': 3.0, 'y_m': 1.0, 'z_m': 1.0}},
            ],
            'measurement_point': {'point_id': 'MLP', 'label': 'MLP', 'position': {'x_m': 2.0, 'y_m': 3.5, 'z_m': 1.0}},
            'avr': {'manufacturer': 'Yamaha', 'model': 'RX-A4A'},
        },
    }


def test_decimal_snap_is_stable() -> None:
    assert snap_scalar(1.024, 0.01) == 1.02
    assert snap_scalar(1.025, 0.01) == 1.03


def test_move_preserves_unknown_aim_and_supports_undo_redo() -> None:
    draft = ContextDraft('project-1', source_context())
    assert draft.payload['speakers'][0].get('aim_xyz') is None
    draft.move_entity('FL', (1.234, 1.111, 0.999), snap_m=0.01)
    assert draft.payload['speakers'][0]['position'] == {'x_m': 1.23, 'y_m': 1.11, 'z_m': 1.0}
    assert draft.payload['speakers'][0].get('aim_xyz') is None
    assert draft.undo() is True
    assert draft.payload['speakers'][0]['position']['x_m'] == 1.0
    assert draft.redo() is True
    assert draft.payload['speakers'][0]['position']['x_m'] == 1.23


def test_explicit_aim_is_normalized_only_when_set() -> None:
    draft = ContextDraft('project-1', source_context())
    draft.set_speaker_aim('FL', (2.0, 0.0, 0.0))
    assert draft.payload['speakers'][0]['aim_xyz'] == [1.0, 0.0, 0.0]
    assert normalize_direction((0.0, 3.0, 4.0)) == pytest.approx((0.0, 0.6, 0.8))
