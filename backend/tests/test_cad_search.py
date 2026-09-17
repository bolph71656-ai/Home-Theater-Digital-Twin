from __future__ import annotations

import pytest

from htdt.cad_constraint_models import (
    CadConstraintPoint2D,
    CadConstraintSet,
    CadExclusionRegionConstraint,
)
from htdt.cad_document import WorkingDocument
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, RoomPrism, SceneDocument, SceneEntity, Size3
from htdt.cad_search import (
    apply_candidate_positions,
    build_cad_search_spec,
    candidate_preview_document,
    generate_cad_candidates,
    search_spec_current,
    search_spec_current_working,
)
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository


DOCUMENT_ID = 'n80-search-fixture'


def _scene(*, speaker_x: float = 1.0) -> SceneDocument:
    return SceneDocument(
        document_id=DOCUMENT_ID,
        schema_version=2,
        room=RoomPrism(width_m=6.0, depth_m=4.0, height_m=2.4),
        entities=(
            SceneEntity(
                entity_id='speaker-fl',
                kind='speaker',
                name='FL',
                position=Position3(x_m=speaker_x, y_m=1.0, z_m=1.0),
                size_m=Size3(x_m=0.22, y_m=0.28, z_m=0.42),
                speaker_role='FL',
            ),
            SceneEntity(
                entity_id='point-mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=3.0, y_m=3.0, z_m=1.1),
            ),
        ),
    )


def _constraints(*, center_x: float = 2.0) -> CadConstraintSet:
    half = 0.2
    return CadConstraintSet(
        document_id=DOCUMENT_ID,
        constraints=(
            CadExclusionRegionConstraint(
                constraint_id='rack-zone',
                name='Rack exclusion',
                entity_ids=('speaker-fl',),
                vertices=(
                    CadConstraintPoint2D(x_m=center_x - half, y_m=0.8),
                    CadConstraintPoint2D(x_m=center_x + half, y_m=0.8),
                    CadConstraintPoint2D(x_m=center_x + half, y_m=1.2),
                    CadConstraintPoint2D(x_m=center_x - half, y_m=1.2),
                ),
            ),
        ),
    )


def _build(repository: SceneRepository):
    revision = repository.save(_scene(), parent_revision_id=None).revision
    spec, estimate = build_cad_search_spec(
        revision,
        _constraints(),
        (CadSearchAxis(entity_id='speaker-fl', axis='x', min_m=1.0, max_m=3.0, step_m=1.0),),
        candidate_limit=10,
        name='FL X sweep',
    )
    return revision, spec, estimate


def test_native_search_spec_round_trip_and_deterministic_generation(tmp_path) -> None:
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision, spec, estimate = _build(scene_repository)
    search_repository = CadSearchRepository(scene_repository)

    assert estimate['raw_candidate_count'] == 3
    search_repository.save(spec)
    loaded = search_repository.get(spec.search_spec_id)
    assert loaded == spec
    assert search_repository.list_specs(DOCUMENT_ID) == (spec,)

    first = generate_cad_candidates(scene_repository, loaded)
    second = generate_cad_candidates(scene_repository, loaded)

    assert first.raw_candidate_count == 3
    assert first.feasible_candidate_count == 2
    assert first.rejected_candidate_count == 1
    assert first.duplicate_candidate_count == 0
    assert first.candidate_set_sha256 == second.candidate_set_sha256
    assert [item.candidate_id for item in first.candidates] == [item.candidate_id for item in second.candidates]
    assert [item.positions['speaker-fl']['x_m'] for item in first.candidates] == [1.0, 3.0]
    assert search_spec_current(spec, revision, _constraints())


def test_search_spec_keeps_constraint_snapshot_but_current_apply_gate_detects_stale(tmp_path) -> None:
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision, spec, _ = _build(scene_repository)
    original = generate_cad_candidates(scene_repository, spec)

    changed_constraints = _constraints(center_x=4.0)
    assert not search_spec_current(spec, revision, changed_constraints)
    regenerated = generate_cad_candidates(scene_repository, spec)
    assert regenerated.candidate_set_sha256 == original.candidate_set_sha256

    changed_scene = _scene(speaker_x=1.1)
    newer_revision = scene_repository.save(changed_scene, parent_revision_id=revision.revision_id).revision
    assert not search_spec_current(spec, newer_revision, _constraints())


def test_candidate_preview_is_non_authoritative_and_apply_is_one_undo(tmp_path) -> None:
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision, spec, _ = _build(scene_repository)
    page = generate_cad_candidates(scene_repository, spec)
    candidate = page.candidates[-1]
    constraints = _constraints()
    working = WorkingDocument(
        revision.document,
        source_revision_id=revision.revision_id,
        saved_content_hash=revision.content_hash,
    )

    preview = candidate_preview_document(working.committed_document, candidate)
    assert preview.entity('speaker-fl').position.x_m == 3.0
    assert working.committed_document.entity('speaker-fl').position.x_m == 1.0
    assert working.history_length == 0
    assert not working.is_dirty
    assert search_spec_current_working(spec, working, constraints)

    assert apply_candidate_positions(working, candidate, spec=spec, current_constraint_set=constraints)
    assert working.committed_document.entity('speaker-fl').position.x_m == 3.0
    assert working.history_length == 1
    assert working.is_dirty

    assert working.undo()
    assert working.committed_document.entity('speaker-fl').position.x_m == 1.0
    assert not working.is_dirty


def test_candidate_apply_rejects_dirty_or_constraint_stale_working_state(tmp_path) -> None:
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision, spec, _ = _build(scene_repository)
    candidate = generate_cad_candidates(scene_repository, spec).candidates[-1]
    working = WorkingDocument(
        revision.document,
        source_revision_id=revision.revision_id,
        saved_content_hash=revision.content_hash,
    )

    working.move_entity('speaker-fl', Position3(x_m=1.2, y_m=1.0, z_m=1.0))
    with pytest.raises(ValueError, match='stale SearchSpec'):
        apply_candidate_positions(working, candidate, spec=spec, current_constraint_set=_constraints())

    working.undo()
    with pytest.raises(ValueError, match='stale SearchSpec'):
        apply_candidate_positions(
            working,
            candidate,
            spec=spec,
            current_constraint_set=_constraints(center_x=4.0),
        )
