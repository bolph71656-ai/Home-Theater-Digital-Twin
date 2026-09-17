from __future__ import annotations

import json
from pathlib import Path

import pytest

from htdt.cad_prediction_jobs import PredictionJobApplyContext, PredictionJobGuard
from htdt.cad_prediction_repository import CadPredictionRepository
from htdt.cad_predictions import (
    RECTANGULAR_GEOMETRY_MODEL_ID,
    RECTANGULAR_GEOMETRY_MODEL_VERSION,
    analyze_native_rectangular_geometry,
    exact_rectangular_room_frame,
)
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import (
    Offset3,
    Position3,
    RoomVertex,
    SceneDocument,
    SceneEntity,
    Size3,
    make_polygon_room,
)


def _speaker(entity_id: str, x_m: float, y_m: float, z_m: float = 1.0) -> SceneEntity:
    return SceneEntity(
        entity_id=entity_id,
        kind='speaker',
        name=entity_id,
        position=Position3(x_m=x_m, y_m=y_m, z_m=z_m),
        size_m=Size3(x_m=0.2, y_m=0.25, z_m=0.4),
        acoustic_reference_offset_m=Offset3(),
        speaker_role='FL',
    )


def _shifted_rect_scene(document_id: str = 'prediction-rect') -> SceneDocument:
    room = make_polygon_room(
        (
            RoomVertex(vertex_id='a', x_m=10.0, y_m=20.0),
            RoomVertex(vertex_id='b', x_m=16.0, y_m=20.0),
            RoomVertex(vertex_id='c', x_m=16.0, y_m=24.0),
            RoomVertex(vertex_id='d', x_m=10.0, y_m=24.0),
        ),
        height_m=2.4,
    )
    return SceneDocument(
        document_id=document_id,
        schema_version=2,
        room=room,
        entities=(
            _speaker('speaker-fl', 11.4, 20.8, 1.05),
            SceneEntity(
                entity_id='point-mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=13.0, y_m=23.0, z_m=1.1),
            ),
        ),
    )


def _l_scene(document_id: str = 'prediction-l') -> SceneDocument:
    room = make_polygon_room(
        (
            RoomVertex(vertex_id='a', x_m=0.0, y_m=0.0),
            RoomVertex(vertex_id='b', x_m=6.0, y_m=0.0),
            RoomVertex(vertex_id='c', x_m=6.0, y_m=4.0),
            RoomVertex(vertex_id='d', x_m=4.0, y_m=4.0),
            RoomVertex(vertex_id='e', x_m=4.0, y_m=2.0),
            RoomVertex(vertex_id='f', x_m=2.0, y_m=2.0),
            RoomVertex(vertex_id='g', x_m=2.0, y_m=4.0),
            RoomVertex(vertex_id='h', x_m=0.0, y_m=4.0),
        ),
        height_m=2.4,
    )
    return SceneDocument(
        document_id=document_id,
        schema_version=2,
        room=room,
        entities=(
            _speaker('speaker-fl', 1.0, 0.8),
            SceneEntity(
                entity_id='point-mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=1.0, y_m=1.5, z_m=1.1),
            ),
        ),
    )


def _saved(tmp_path: Path, scene: SceneDocument):
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision = repository.save(scene, parent_revision_id=None).revision
    return repository, revision


def test_shifted_axis_aligned_rectangle_is_exact_and_reflections_return_world_coordinates(tmp_path: Path) -> None:
    _, revision = _saved(tmp_path, _shifted_rect_scene())

    frame = exact_rectangular_room_frame(revision.document.room)
    assert frame is not None
    assert (frame.origin_x_m, frame.origin_y_m, frame.width_m, frame.depth_m) == (10.0, 20.0, 6.0, 4.0)

    modes, reflections = analyze_native_rectangular_geometry(revision, 'point-mlp', max_mode_hz=120.0)

    assert modes.run_id == reflections.run_id
    assert modes.model_id == RECTANGULAR_GEOMETRY_MODEL_ID
    assert modes.model_version == RECTANGULAR_GEOMETRY_MODEL_VERSION
    assert modes.geometry_compatibility == 'exact_for_model_geometry'
    assert reflections.geometry_compatibility == 'exact_for_model_geometry'
    assert modes.modes
    assert len(reflections.reflections) == 6
    assert not reflections.warnings
    assert all(10.0 <= item.reflection_position.x_m <= 16.0 for item in reflections.reflections)
    assert all(20.0 <= item.reflection_position.y_m <= 24.0 for item in reflections.reflections)
    assert {item.surface_key for item in reflections.reflections} == {
        'left_x0', 'right_xW', 'front_y0', 'rear_yD', 'floor_z0', 'ceiling_zH'
    }
    snapshot = json.loads(reflections.input_snapshot_json)
    assert snapshot['room_frame']['origin_x_m'] == 10.0
    assert snapshot['room_frame']['origin_y_m'] == 20.0
    assert snapshot['approximation_rule'] is None


def test_nonrectangular_room_is_explicitly_unsupported_not_silently_approximated(tmp_path: Path) -> None:
    _, revision = _saved(tmp_path, _l_scene())

    assert exact_rectangular_room_frame(revision.document.room) is None
    modes, reflections = analyze_native_rectangular_geometry(revision, 'point-mlp')

    assert modes.geometry_compatibility == 'unsupported'
    assert reflections.geometry_compatibility == 'unsupported'
    assert modes.modes == ()
    assert reflections.reflections == ()
    assert modes.warnings == ('rectangular_geometry_model_requires_axis_aligned_rectangular_room',)
    snapshot = json.loads(modes.input_snapshot_json)
    assert snapshot['approximation_rule'] is None
    assert len(snapshot['room']['footprint_vertices']) == 8


def test_prediction_repository_round_trip_preserves_exact_revision_model_and_input(tmp_path: Path) -> None:
    scene_repository, revision = _saved(tmp_path, _shifted_rect_scene())
    prediction_repository = CadPredictionRepository(scene_repository)
    results = analyze_native_rectangular_geometry(revision, 'point-mlp', max_mode_hz=150.0)

    for result in results:
        prediction_repository.save(result)

    assert prediction_repository.list_results(revision.document_id) == results
    assert prediction_repository.list_run(results[0].run_id) == results
    assert prediction_repository.get(results[0].prediction_id) == results[0]

    wrong_hash = results[0].model_copy(update={'scene_content_hash': '0' * 64})
    with pytest.raises(ValueError, match='content hash'):
        prediction_repository.save(wrong_hash)


def test_prediction_job_guard_rejects_superseded_cancelled_revision_and_constraint_stale_results(tmp_path: Path) -> None:
    _, revision = _saved(tmp_path, _shifted_rect_scene())
    guard = PredictionJobGuard()
    active = PredictionJobApplyContext(
        document_id=revision.document_id,
        scene_revision_id=revision.revision_id,
        scene_content_hash=revision.content_hash,
        constraint_workspace_hash='1' * 64,
    )

    first = guard.submit(
        revision,
        model_id=RECTANGULAR_GEOMETRY_MODEL_ID,
        model_version=RECTANGULAR_GEOMETRY_MODEL_VERSION,
        parameters_json='{}',
        input_hash='a' * 64,
        constraint_workspace_hash='1' * 64,
    )
    assert guard.can_apply(first, active)

    second = guard.submit(
        revision,
        model_id=RECTANGULAR_GEOMETRY_MODEL_ID,
        model_version=RECTANGULAR_GEOMETRY_MODEL_VERSION,
        parameters_json='{}',
        input_hash='b' * 64,
        constraint_workspace_hash='1' * 64,
    )
    assert not guard.can_apply(first, active)
    assert guard.can_apply(second, active)

    guard.cancel(second)
    assert guard.is_cancelled(second)
    assert not guard.can_apply(second, active)

    third = guard.submit(
        revision,
        model_id=RECTANGULAR_GEOMETRY_MODEL_ID,
        model_version=RECTANGULAR_GEOMETRY_MODEL_VERSION,
        parameters_json='{}',
        input_hash='c' * 64,
        constraint_workspace_hash='1' * 64,
    )
    stale_revision = PredictionJobApplyContext(
        document_id=revision.document_id,
        scene_revision_id='later-revision',
        scene_content_hash='f' * 64,
        constraint_workspace_hash='1' * 64,
    )
    stale_constraint = PredictionJobApplyContext(
        document_id=revision.document_id,
        scene_revision_id=revision.revision_id,
        scene_content_hash=revision.content_hash,
        constraint_workspace_hash='2' * 64,
    )
    other_document = PredictionJobApplyContext(
        document_id='other-document',
        scene_revision_id=revision.revision_id,
        scene_content_hash=revision.content_hash,
        constraint_workspace_hash='1' * 64,
    )
    assert not guard.can_apply(third, stale_revision)
    assert not guard.can_apply(third, stale_constraint)
    assert not guard.can_apply(third, other_document)
    assert guard.can_apply(third, active)
