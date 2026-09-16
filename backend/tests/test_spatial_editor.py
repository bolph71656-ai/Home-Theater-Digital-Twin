from __future__ import annotations

import pytest

from htdt.spatial_editor import ContextDraft, SpatialEditError, normalize_direction, snap_scalar


def source_context(*, polygon: bool = False) -> dict:
    room = {'width_m': 4.0, 'depth_m': 5.0, 'height_m': 2.4, 'geometry_kind': 'rectangular'}
    if polygon:
        room = {
            'width_m': 4.0,
            'depth_m': 5.0,
            'height_m': 2.4,
            'geometry_kind': 'polygon_prism',
            'footprint_vertices': [
                {'vertex_id': 'v0', 'x_m': 0.0, 'y_m': 0.0},
                {'vertex_id': 'v1', 'x_m': 4.0, 'y_m': 0.0},
                {'vertex_id': 'v2', 'x_m': 4.0, 'y_m': 5.0},
                {'vertex_id': 'v3', 'x_m': 2.5, 'y_m': 5.0},
                {'vertex_id': 'v4', 'x_m': 2.5, 'y_m': 4.0},
                {'vertex_id': 'v5', 'x_m': 1.5, 'y_m': 4.0},
                {'vertex_id': 'v6', 'x_m': 1.5, 'y_m': 5.0},
                {'vertex_id': 'v7', 'x_m': 0.0, 'y_m': 5.0},
            ],
        }
    return {
        'id': 'ctx-1', 'revision_number': 7,
        'payload': {
            'room': room,
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


def test_polygon_vertex_edit_is_snapped_validated_and_undoable() -> None:
    draft = ContextDraft('project-1', source_context(polygon=True))
    draft.move_room_vertex('v4', (2.42, 3.92), snap_m=0.1)
    vertex = next(v for v in draft.payload['room']['footprint_vertices'] if v['vertex_id'] == 'v4')
    assert vertex == {'vertex_id': 'v4', 'x_m': 2.4, 'y_m': 3.9}
    assert draft.undo() is True
    restored = next(v for v in draft.payload['room']['footprint_vertices'] if v['vertex_id'] == 'v4')
    assert restored['x_m'] == 2.5 and restored['y_m'] == 4.0


def test_invalid_polygon_edit_is_not_committed() -> None:
    draft = ContextDraft('project-1', source_context(polygon=True))
    before = draft.payload
    with pytest.raises(SpatialEditError):
        draft.move_room_vertex('v4', (4.5, 4.0), snap_m=0.1)
    assert draft.payload == before


def test_payload_for_save_links_new_revision_to_source_context() -> None:
    draft = ContextDraft('project-1', source_context())
    draft.move_entity('MLP', (2.0, 3.4, 1.0), snap_m=0.1)
    saved = draft.payload_for_save()
    assert saved['parent_context_id'] == 'ctx-1'
    assert saved['measurement_point']['position']['y_m'] == 3.4
