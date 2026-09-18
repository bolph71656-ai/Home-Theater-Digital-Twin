from __future__ import annotations

import pytest
from hashlib import sha256

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_measurement_loop import build_measurement_plan, complete_measurement_plan
from htdt.cad_measurement_models import CadFrequencyResponseDataset, CadMeasurementRecord
from htdt.cad_measurement_repository import CadMeasurementRepository
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
            speaker_role='FL'),
            SceneEntity(entity_id='mlp', kind='measurement_point', name='MLP',
                position=Position3(x_m=2.5,y_m=3,z_m=1)),),
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

    measurement_repo = CadMeasurementRepository(scene_repo)
    tampered_plan = plan.model_copy(update={'plan_sha256': '0' * 64})
    with pytest.raises(ValueError, match='identity hash mismatch'):
        measurement_repo.save_measurement_plan(tampered_plan)
    measurement_repo.save_measurement_plan(plan)
    raw = b'o50-measured-fr'
    record = CadMeasurementRecord(
        measurement_id='measurement-a',
        document_id=applied.document_id,
        scene_revision_id=applied.revision_id,
        scene_content_hash=applied.content_hash,
        measurement_entity_id='mlp',
        measurement_position=applied.document.entity('mlp').position,
        evidence_type='measured',
        channel_role='FL',
        source_speaker_ids=('fl',),
        radiation_scope='single',
        routing_evidence='manual',
        imported_at='2026-09-18T00:00:00+00:00',
        source_kind='rew_text',
    )
    dataset = CadFrequencyResponseDataset(
        dataset_id='dataset-a',
        measurement_id=record.measurement_id,
        frequency_hz=(20.0, 40.0, 80.0),
        level_db=(80.0, 81.0, 79.0),
        phase_deg=None,
        phase_status='absent',
        source_sha256=sha256(raw).hexdigest(),
        importer_version='fixture-1',
    )
    measurement_repo.save(record, dataset, raw_filename='fixture.txt', raw_bytes=raw)
    completed = complete_measurement_plan(plan, measurement_repo, (record.measurement_id,))
    measurement_repo.save_measurement_plan(completed)

    assert completed.status == 'measured'
    assert completed.measurement_ids == ('measurement-a',)
    assert measurement_repo.latest_measurement_plans(spec.search_spec_id) == (completed,)


def test_measurement_plan_rejects_unknown_candidate_and_non_candidate_revision(tmp_path):
    scene_repo = SceneRepository(tmp_path / 'cad.sqlite3')
    document = SceneDocument(
        document_id='o50-reject', schema_version=2,
        room=RoomPrism(width_m=5, depth_m=4, height_m=2.4),
        entities=(SceneEntity(entity_id='fl', kind='speaker', name='FL',
            position=Position3(x_m=1,y_m=1,z_m=1), size_m=Size3(x_m=.2,y_m=.2,z_m=.4),
            speaker_role='FL'),
            SceneEntity(entity_id='mlp', kind='measurement_point', name='MLP',
                position=Position3(x_m=2.5,y_m=3,z_m=1)),),
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
