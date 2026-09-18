from __future__ import annotations

import pytest

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_measurement_loop import build_measurement_plan
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, RoomPrism, SceneDocument, SceneEntity, Size3
from htdt.cad_search import build_cad_search_spec, generate_cad_candidates, apply_candidate_positions
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository
from htdt.cad_document import WorkingDocument


def test_measurement_plan_binds_candidate_to_exact_applied_revision(tmp_path):
    scene_repo = SceneRepository(tmp_path / 'cad.sqlite3')
    document = SceneDocument(
        document_id='o50-fixture', schema_version=2,
        room=RoomPrism(width_m=5, depth_m=4, height_m=2.4),
        entities=(SceneEntity(entity_id='fl', kind='speaker', name='FL',
            position=Position3(x_m=1,y_m=1,z_m=1), size_m=Size3(x_m=.2,y_m=.2,z_m=.4),
            speaker_role='FL'),),
    )
    source = scene_repo.save(document, parent_revision_id=None).revision
    spec,_ = build_cad_search_spec(source, CadConstraintSet(document_id='o50-fixture', constraints=()),
        (CadSearchAxis(entity_id='fl',axis='x',min_m=1,max_m=2,step_m=1),), candidate_limit=10)
    search_repo = CadSearchRepository(scene_repo); search_repo.save(spec)
    page = generate_cad_candidates(scene_repo, spec)
    candidate = page.candidates[1]
    working = WorkingDocument(source.document, source_revision_id=source.revision_id)
    constraint_set = CadConstraintSet(document_id='o50-fixture', constraints=())
    apply_candidate_positions(working, candidate, spec=spec, current_constraint_set=constraint_set)
    applied = scene_repo.save(working.committed_document, parent_revision_id=source.revision_id).revision

    plan = build_measurement_plan(scene_repo, search_repo, search_spec_id=spec.search_spec_id,
        candidate_id=candidate.candidate_id, applied_scene_revision_id=applied.revision_id)

    assert plan.candidate_id == candidate.candidate_id
    assert plan.applied_scene_revision_id == applied.revision_id
    assert plan.applied_scene_content_hash == applied.content_hash
    assert plan.candidate_set_sha256 == page.candidate_set_sha256
    assert plan.status == 'planned'


def test_measurement_plan_rejects_unknown_candidate_and_non_candidate_revision(tmp_path):
    scene_repo = SceneRepository(tmp_path / 'cad.sqlite3')
    document = SceneDocument(
        document_id='o50-reject', schema_version=2,
        room=RoomPrism(width_m=5, depth_m=4, height_m=2.4),
        entities=(SceneEntity(entity_id='fl', kind='speaker', name='FL',
            position=Position3(x_m=1,y_m=1,z_m=1), size_m=Size3(x_m=.2,y_m=.2,z_m=.4),
            speaker_role='FL'),),
    )
    source = scene_repo.save(document, parent_revision_id=None).revision
    constraints = CadConstraintSet(document_id='o50-reject', constraints=())
    spec,_ = build_cad_search_spec(source, constraints,
        (CadSearchAxis(entity_id='fl',axis='x',min_m=1,max_m=2,step_m=1),), candidate_limit=10)
    search_repo = CadSearchRepository(scene_repo)
    search_repo.save(spec)
    candidate = generate_cad_candidates(scene_repo, spec).candidates[1]

    wrong_document = source.document.model_copy(update={'entities': (
        source.document.entity('fl').model_copy(update={'position': Position3(x_m=2,y_m=1.25,z_m=1)}),
    )})
    wrong_revision = scene_repo.save(wrong_document, parent_revision_id=source.revision_id).revision

    with pytest.raises(ValueError, match='candidate does not belong'):
        build_measurement_plan(scene_repo, search_repo, search_spec_id=spec.search_spec_id,
            candidate_id='not-a-candidate', applied_scene_revision_id=wrong_revision.revision_id)
    with pytest.raises(ValueError, match='does not exactly match'):
        build_measurement_plan(scene_repo, search_repo, search_spec_id=spec.search_spec_id,
            candidate_id=candidate.candidate_id, applied_scene_revision_id=wrong_revision.revision_id)
