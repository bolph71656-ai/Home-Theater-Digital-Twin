from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from htdt.cad_constraint_models import CadConstraintSet, CadWallClearanceConstraint
from htdt.cad_document import WorkingDocument
from htdt.cad_extended_search import (
    CadExtendedSearchAxis,
    aim_horizontal_yaw_deg,
    body_horizontal_yaw_deg,
    apply_extended_candidate,
    build_extended_model_capability,
    build_extended_search_spec,
    extended_candidate_preview_document,
    generate_extended_candidates,
)
from htdt.cad_extended_search_repository import CadExtendedSearchRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import (
    Direction3,
    Offset3,
    Position3,
    RoomPrism,
    SceneDocument,
    SceneEntity,
    Size3,
)
from htdt.cad_search import build_cad_search_spec, generate_cad_candidates
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository
from htdt.cad_walls import make_wall_topology


DOCUMENT_ID = 'o80-extended-fixture'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scene() -> SceneDocument:
    return SceneDocument(
        document_id=DOCUMENT_ID,
        schema_version=2,
        room=RoomPrism(width_m=5.0, depth_m=4.0, height_m=2.4),
        entities=(
            SceneEntity(
                entity_id='fl',
                kind='speaker',
                name='FL',
                speaker_role='FL',
                position=Position3(x_m=1.0, y_m=1.0, z_m=1.0),
                size_m=Size3(x_m=0.2, y_m=0.2, z_m=0.4),
                acoustic_reference_offset_m=Offset3(),
                aim_xyz=Direction3(x=0.0, y=1.0, z=0.0),
            ),
            SceneEntity(
                entity_id='mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=2.5, y_m=3.0, z_m=1.1),
            ),
        ),
    )


def _fixture(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision = scene_repository.save(_scene(), parent_revision_id=None).revision
    constraints = CadConstraintSet(document_id=DOCUMENT_ID, constraints=())
    base_spec, _estimate = build_cad_search_spec(
        revision,
        constraints,
        (
            CadSearchAxis(
                entity_id='fl',
                axis='x',
                min_m=1.0,
                max_m=1.2,
                step_m=0.2,
            ),
        ),
        candidate_limit=20,
        name='base position sweep',
    )
    search_repository = CadSearchRepository(scene_repository)
    search_repository.save(base_spec)
    base_page = generate_cad_candidates(scene_repository, base_spec, limit=20)
    capability = build_extended_model_capability(
        model_id='synthetic-directional-fixture',
        model_version='1',
        evidence_scope='synthetic_fixture',
        supported_parameters=('aim_yaw_deg', 'body_yaw_deg'),
        detail='synthetic directional model for software acceptance only',
        created_at_utc=_now(),
    )
    extended_repository = CadExtendedSearchRepository(search_repository)
    extended_repository.save_capability(capability)
    spec = build_extended_search_spec(
        source_revision=revision,
        base_spec=base_spec,
        base_candidate_set_sha256=base_page.candidate_set_sha256,
        base_candidate_count=base_page.feasible_candidate_count,
        capability=capability,
        axes=(
            CadExtendedSearchAxis(
                entity_id='fl',
                min_value=-15.0,
                max_value=15.0,
                step=15.0,
            ),
        ),
        candidate_limit=20,
        created_at_utc=_now(),
    )
    extended_repository.save_spec(spec)
    return (
        scene_repository,
        revision,
        constraints,
        base_spec,
        base_page,
        capability,
        extended_repository,
        spec,
    )


def test_extended_search_is_deterministic_and_layers_on_base_candidate_set(tmp_path):
    (
        scene_repository,
        _revision,
        _constraints,
        base_spec,
        base_page,
        _capability,
        repository,
        spec,
    ) = _fixture(tmp_path)

    first = generate_extended_candidates(
        scene_repository,
        base_spec,
        spec,
        limit=20,
    )
    second = generate_extended_candidates(
        scene_repository,
        base_spec,
        spec,
        limit=20,
    )

    assert base_page.feasible_candidate_count == 2
    assert first.feasible_candidate_count == 6
    assert first.raw_candidate_count == 6
    assert first.candidate_set_sha256 == second.candidate_set_sha256
    assert [item.candidate_id for item in first.candidates] == [
        item.candidate_id for item in second.candidates
    ]
    assert [item.aim_yaw_deg['fl'] for item in first.candidates] == [
        -15.0, 0.0, 15.0, -15.0, 0.0, 15.0
    ]
    assert repository.get_spec(spec.extended_search_id) == spec


def test_extended_preview_and_apply_change_position_and_aim_in_one_undo(tmp_path):
    (
        scene_repository,
        revision,
        constraints,
        base_spec,
        _base_page,
        _capability,
        _repository,
        spec,
    ) = _fixture(tmp_path)
    page = generate_extended_candidates(scene_repository, base_spec, spec, limit=20)
    candidate = page.candidates[-1]
    working = WorkingDocument(
        revision.document,
        source_revision_id=revision.revision_id,
        saved_content_hash=revision.content_hash,
    )

    preview = extended_candidate_preview_document(
        working.committed_document,
        candidate,
    )
    assert preview.entity('fl').position.x_m == pytest.approx(1.2)
    assert aim_horizontal_yaw_deg(preview.entity('fl').aim_xyz) == pytest.approx(15.0)
    assert working.committed_document.entity('fl').position.x_m == pytest.approx(1.0)
    assert aim_horizontal_yaw_deg(
        working.committed_document.entity('fl').aim_xyz
    ) == pytest.approx(0.0)

    assert apply_extended_candidate(
        working,
        candidate,
        extended_spec=spec,
        base_spec=base_spec,
        current_constraint_set=constraints,
        current_document_id=DOCUMENT_ID,
    )
    assert working.history_length == 1
    assert working.committed_document.entity('fl').position.x_m == pytest.approx(1.2)
    assert aim_horizontal_yaw_deg(
        working.committed_document.entity('fl').aim_xyz
    ) == pytest.approx(15.0)

    assert working.undo()
    assert not working.is_dirty
    assert working.committed_document.entity('fl').position.x_m == pytest.approx(1.0)
    assert aim_horizontal_yaw_deg(
        working.committed_document.entity('fl').aim_xyz
    ) == pytest.approx(0.0)


def test_extended_apply_rejects_position_tampering_even_with_base_candidate_id(tmp_path):
    (
        scene_repository,
        revision,
        constraints,
        base_spec,
        _base_page,
        _capability,
        _repository,
        spec,
    ) = _fixture(tmp_path)
    page = generate_extended_candidates(scene_repository, base_spec, spec, limit=20)
    candidate = page.candidates[-1]
    tampered_positions = {
        entity_id: dict(position)
        for entity_id, position in candidate.positions.items()
    }
    tampered_positions['fl']['x_m'] = 1.1
    tampered = candidate.model_copy(update={'positions': tampered_positions})
    working = WorkingDocument(
        revision.document,
        source_revision_id=revision.revision_id,
        saved_content_hash=revision.content_hash,
    )

    with pytest.raises(ValueError, match='identity mismatch'):
        apply_extended_candidate(
            working,
            tampered,
            extended_spec=spec,
            base_spec=base_spec,
            current_constraint_set=constraints,
            current_document_id=DOCUMENT_ID,
        )


def test_rew_roomsim_cannot_claim_toe_in_capability():
    with pytest.raises(ValueError, match='does not model speaker acoustic direction'):
        build_extended_model_capability(
            model_id='rew-room-simulator',
            model_version='5.40',
            evidence_scope='synthetic_fixture',
            supported_parameters=('aim_yaw_deg', 'body_yaw_deg'),
            detail='invalid',
            created_at_utc=_now(),
        )


def test_extended_search_requires_explicit_source_aim(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    document = _scene()
    speaker = document.entity('fl').model_copy(update={'aim_xyz': None})
    no_aim = document.model_copy(update={
        'entities': tuple(
            speaker if entity.entity_id == 'fl' else entity
            for entity in document.entities
        )
    })
    revision = scene_repository.save(no_aim, parent_revision_id=None).revision
    constraints = CadConstraintSet(document_id=DOCUMENT_ID, constraints=())
    base_spec, _ = build_cad_search_spec(
        revision,
        constraints,
        (
            CadSearchAxis(
                entity_id='fl',
                axis='x',
                min_m=1.0,
                max_m=1.0,
                step_m=0.1,
            ),
        ),
        candidate_limit=10,
    )
    base_page = generate_cad_candidates(scene_repository, base_spec)
    capability = build_extended_model_capability(
        model_id='synthetic-directional-fixture',
        model_version='1',
        evidence_scope='synthetic_fixture',
        supported_parameters=('aim_yaw_deg', 'body_yaw_deg'),
        detail='fixture',
        created_at_utc=_now(),
    )

    with pytest.raises(ValueError, match='requires explicit speaker aim'):
        build_extended_search_spec(
            source_revision=revision,
            base_spec=base_spec,
            base_candidate_set_sha256=base_page.candidate_set_sha256,
            base_candidate_count=base_page.feasible_candidate_count,
            capability=capability,
            axes=(CadExtendedSearchAxis(
                entity_id='fl',
                min_value=-10.0,
                max_value=10.0,
                step=10.0,
            ),),
            candidate_limit=10,
            created_at_utc=_now(),
        )

class _ValidationRepository:
    def __init__(self, path, record):
        self.path = path
        self.record = record

    def get(self, validation_id):
        return (
            self.record
            if validation_id == self.record.validation_id
            else None
        )


def test_owned_room_extended_spec_requires_exact_o60_search_authority(tmp_path):
    (
        scene_repository,
        revision,
        _constraints,
        base_spec,
        base_page,
        _capability,
        _repository,
        _spec,
    ) = _fixture(tmp_path)
    validation = SimpleNamespace(
        validation_id='owned-directional-validation',
        evidence_scope='owned_room',
        recommendation_gate='eligible',
        gate_reasons=(),
        campaign_id='owned-directional-campaign',
        campaign_sha256='a' * 64,
        model_id='owned-directional-model',
        model_version='1',
        document_id=DOCUMENT_ID,
        search_spec_id='different-search-spec',
        search_spec_sha256='b' * 64,
        candidate_set_sha256='c' * 64,
    )
    validation_repository = _ValidationRepository(
        scene_repository.path,
        validation,
    )
    repository = CadExtendedSearchRepository(
        CadSearchRepository(scene_repository),
        validation_repository,
    )
    capability = build_extended_model_capability(
        model_id=validation.model_id,
        model_version=validation.model_version,
        evidence_scope='owned_room',
        supported_parameters=('aim_yaw_deg', 'body_yaw_deg'),
        detail='owned-room directional fixture',
        validation=validation,
        created_at_utc=_now(),
    )
    repository.save_capability(capability)
    spec = build_extended_search_spec(
        source_revision=revision,
        base_spec=base_spec,
        base_candidate_set_sha256=base_page.candidate_set_sha256,
        base_candidate_count=base_page.feasible_candidate_count,
        capability=capability,
        axes=(
            CadExtendedSearchAxis(
                entity_id='fl',
                min_value=-10.0,
                max_value=10.0,
                step=10.0,
            ),
        ),
        candidate_limit=20,
        created_at_utc=_now(),
    )

    with pytest.raises(
        ValueError,
        match='does not match exact base SearchSpec/candidate-set',
    ):
        repository.save_spec(spec)



def test_physical_toe_in_rotates_body_and_coupled_aim_in_one_undo(tmp_path):
    (
        scene_repository,
        revision,
        constraints,
        base_spec,
        base_page,
        capability,
        _repository,
        _aim_spec,
    ) = _fixture(tmp_path)
    body_spec = build_extended_search_spec(
        source_revision=revision,
        base_spec=base_spec,
        base_candidate_set_sha256=base_page.candidate_set_sha256,
        base_candidate_count=base_page.feasible_candidate_count,
        capability=capability,
        axes=(
            CadExtendedSearchAxis(
                entity_id='fl',
                parameter='body_yaw_deg',
                min_value=-15.0,
                max_value=15.0,
                step=15.0,
            ),
        ),
        candidate_limit=20,
        created_at_utc=_now(),
    )
    page = generate_extended_candidates(
        scene_repository,
        base_spec,
        body_spec,
        limit=20,
    )
    candidate = page.candidates[-1]
    assert candidate.body_yaw_deg == {'fl': 15.0}
    assert candidate.aim_yaw_deg == {}

    preview = extended_candidate_preview_document(revision.document, candidate)
    preview_speaker = preview.entity('fl')
    assert body_horizontal_yaw_deg(preview_speaker) == pytest.approx(15.0)
    assert aim_horizontal_yaw_deg(preview_speaker.aim_xyz) == pytest.approx(15.0)

    working = WorkingDocument(
        revision.document,
        source_revision_id=revision.revision_id,
        saved_content_hash=revision.content_hash,
    )
    assert apply_extended_candidate(
        working,
        candidate,
        extended_spec=body_spec,
        base_spec=base_spec,
        current_constraint_set=constraints,
        current_document_id=DOCUMENT_ID,
    )
    assert working.history_length == 1
    applied = working.committed_document.entity('fl')
    assert body_horizontal_yaw_deg(applied) == pytest.approx(15.0)
    assert aim_horizontal_yaw_deg(applied.aim_xyz) == pytest.approx(15.0)

    assert working.undo()
    restored = working.committed_document.entity('fl')
    assert body_horizontal_yaw_deg(restored) == pytest.approx(0.0)
    assert aim_horizontal_yaw_deg(restored.aim_xyz) == pytest.approx(0.0)


def test_physical_toe_in_rechecks_exact_oriented_wall_clearance(tmp_path):
    room = RoomPrism(width_m=5.0, depth_m=4.0, height_m=2.4)
    topology = make_wall_topology(room)
    document = SceneDocument(
        document_id='o80p-wall-fixture',
        schema_version=3,
        room=room,
        wall_topology=topology,
        entities=(
            SceneEntity(
                entity_id='fl',
                kind='speaker',
                name='FL',
                speaker_role='FL',
                position=Position3(x_m=0.6, y_m=1.5, z_m=1.0),
                size_m=Size3(x_m=0.2, y_m=1.0, z_m=0.4),
                acoustic_reference_offset_m=Offset3(),
                aim_xyz=Direction3(x=0.0, y=1.0, z=0.0),
            ),
            SceneEntity(
                entity_id='mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=2.5, y_m=3.0, z_m=1.1),
            ),
        ),
    )
    scene_repository = SceneRepository(tmp_path / 'physical.sqlite3')
    revision = scene_repository.save(document, parent_revision_id=None).revision
    left_wall_id = 'wall:rear-left->front-left'
    constraints = CadConstraintSet(
        document_id=document.document_id,
        constraints=(
            CadWallClearanceConstraint(
                constraint_id='left-clearance',
                name='left clearance',
                entity_ids=('fl',),
                wall_id=left_wall_id,
                min_m=0.3,
            ),
        ),
    )
    base_spec, _ = build_cad_search_spec(
        revision,
        constraints,
        (
            CadSearchAxis(
                entity_id='fl',
                axis='x',
                min_m=0.6,
                max_m=0.6,
                step_m=0.1,
            ),
        ),
        candidate_limit=10,
        name='source orientation position',
    )
    base_page = generate_cad_candidates(scene_repository, base_spec, limit=10)

    # Exact source body yaw=0 footprint has x half-extent 0.1 m, so the
    # cabinet clearance is 0.5 m and this XYZ is feasible.
    assert base_page.feasible_candidate_count == 1

    capability = build_extended_model_capability(
        model_id='synthetic-directional-fixture',
        model_version='1',
        evidence_scope='synthetic_fixture',
        supported_parameters=('body_yaw_deg',),
        detail='physical toe-in geometry acceptance',
        created_at_utc=_now(),
    )
    spec = build_extended_search_spec(
        source_revision=revision,
        base_spec=base_spec,
        base_candidate_set_sha256=base_page.candidate_set_sha256,
        base_candidate_count=base_page.feasible_candidate_count,
        capability=capability,
        axes=(
            CadExtendedSearchAxis(
                entity_id='fl',
                parameter='body_yaw_deg',
                min_value=0.0,
                max_value=90.0,
                step=90.0,
            ),
        ),
        candidate_limit=10,
        created_at_utc=_now(),
    )
    page = generate_extended_candidates(
        scene_repository,
        base_spec,
        spec,
        limit=10,
    )

    # At 90 degrees the 1.0 m cabinet depth becomes the x extent, reducing
    # exact wall clearance to 0.1 m. The rotated body must be rejected.
    assert page.raw_candidate_count == 2
    assert page.feasible_candidate_count == 1
    assert page.rejected_candidate_count == 1
    assert page.rejection_counts == {'left-clearance': 1}
    assert [item.body_yaw_deg['fl'] for item in page.candidates] == [0.0]
