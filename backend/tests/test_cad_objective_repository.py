from __future__ import annotations

import pytest

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_objective_models import CadObjectiveInputRef
from htdt.cad_objectives import build_objective_evaluation, build_pareto_set
from htdt.cad_objective_repository import CadObjectiveRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, RoomPrism, SceneDocument, SceneEntity
from htdt.cad_search import build_cad_search_spec, generate_cad_candidates
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository
from htdt.optimization_objectives import ObjectiveMetric, ObjectiveVector


DOCUMENT_ID = 'objective-repository-fixture'


def _scene() -> SceneDocument:
    return SceneDocument(
        document_id=DOCUMENT_ID,
        schema_version=2,
        room=RoomPrism(width_m=6.0, depth_m=4.0, height_m=2.4),
        entities=(
            SceneEntity(
                entity_id='speaker-fl',
                kind='speaker',
                name='FL',
                position=Position3(x_m=1.0, y_m=1.0, z_m=1.0),
                speaker_role='FL',
            ),
        ),
    )


def _fixture(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision = scene_repository.save(_scene(), parent_revision_id=None).revision
    spec, _estimate = build_cad_search_spec(
        revision,
        CadConstraintSet(document_id=DOCUMENT_ID, constraints=()),
        (CadSearchAxis(entity_id='speaker-fl', axis='x', min_m=1.0, max_m=3.0, step_m=1.0),),
        candidate_limit=10,
        name='objective fixture',
    )
    search_repository = CadSearchRepository(scene_repository)
    search_repository.save(spec)
    candidates = generate_cad_candidates(scene_repository, spec).candidates
    objective_repository = CadObjectiveRepository(scene_repository, search_repository)
    return scene_repository, revision, spec, candidates, objective_repository


def _vector(candidate_id: str, response: float, movement: float) -> ObjectiveVector:
    return ObjectiveVector(
        candidate_id=candidate_id,
        metrics=(
            ObjectiveMetric(objective_id='response.shape_rms_db', value=response, unit='dB'),
            ObjectiveMetric(objective_id='movement.total_m', value=movement, unit='m'),
        ),
    )


def _evaluation(revision, spec, candidate_id: str, response: float, movement: float):
    return build_objective_evaluation(
        revision,
        spec,
        candidate_id,
        _vector(candidate_id, response, movement),
        evaluation_spec={
            'algorithm_version': 'objective-vector-1',
            'objectives': ['response.shape_rms_db', 'movement.total_m'],
            'response_band_hz': [20.0, 160.0],
        },
        input_refs=(
            CadObjectiveInputRef(
                evidence_class='derived',
                source_kind='candidate_geometry',
                source_id=candidate_id,
            ),
            CadObjectiveInputRef(
                evidence_class='predicted',
                source_kind='prediction_fixture',
                source_id=f'prediction:{candidate_id}',
            ),
        ),
    )


def test_objective_evaluation_round_trip_is_bound_to_scene_and_search_spec(tmp_path) -> None:
    _scene_repo, revision, spec, candidates, repository = _fixture(tmp_path)
    candidate = candidates[0]
    evaluation = _evaluation(revision, spec, candidate.candidate_id, 2.0, 1.0)

    repository.save_evaluation(evaluation)

    assert repository.get_evaluation(evaluation.evaluation_id) == evaluation
    assert repository.list_evaluations(spec.search_spec_id) == (evaluation,)
    assert evaluation.vector.candidate_id == candidate.candidate_id
    assert evaluation.evaluation_spec_sha256
    assert evaluation.evaluation_sha256


def test_pareto_set_round_trip_recomputes_from_immutable_evaluations(tmp_path) -> None:
    _scene_repo, revision, spec, candidates, repository = _fixture(tmp_path)
    evaluations = (
        _evaluation(revision, spec, candidates[0].candidate_id, 1.0, 3.0),
        _evaluation(revision, spec, candidates[1].candidate_id, 2.0, 2.0),
        _evaluation(revision, spec, candidates[2].candidate_id, 3.0, 3.0),
    )
    for evaluation in evaluations:
        repository.save_evaluation(evaluation)

    pareto_set = build_pareto_set(
        evaluations,
        ('response.shape_rms_db', 'movement.total_m'),
    )
    repository.save_pareto_set(pareto_set)

    assert pareto_set.result.non_dominated_candidate_ids == (
        candidates[0].candidate_id,
        candidates[1].candidate_id,
    )
    assert repository.get_pareto_set(pareto_set.pareto_set_id) == pareto_set
    assert repository.list_pareto_sets(spec.search_spec_id) == (pareto_set,)


def test_objective_repository_rejects_tampered_search_binding(tmp_path) -> None:
    _scene_repo, revision, spec, candidates, repository = _fixture(tmp_path)
    evaluation = _evaluation(revision, spec, candidates[0].candidate_id, 1.0, 1.0)
    tampered = evaluation.model_copy(update={'search_spec_sha256': '0' * 64})

    with pytest.raises(ValueError, match='SearchSpec hash mismatch'):
        repository.save_evaluation(tampered)


def test_pareto_repository_rejects_result_not_matching_evaluations(tmp_path) -> None:
    _scene_repo, revision, spec, candidates, repository = _fixture(tmp_path)
    evaluations = (
        _evaluation(revision, spec, candidates[0].candidate_id, 1.0, 3.0),
        _evaluation(revision, spec, candidates[1].candidate_id, 2.0, 2.0),
    )
    for evaluation in evaluations:
        repository.save_evaluation(evaluation)

    pareto_set = build_pareto_set(
        evaluations,
        ('response.shape_rms_db', 'movement.total_m'),
    )
    wrong_result = pareto_set.result.model_copy(
        update={'non_dominated_candidate_ids': (candidates[0].candidate_id,)}
    )
    tampered_payload = pareto_set.identity_payload()
    tampered_payload['result'] = wrong_result.model_dump(mode='json')
    from htdt.cad_objective_models import canonical_objective_sha256

    tampered = pareto_set.model_copy(update={
        'result': wrong_result,
        'pareto_sha256': canonical_objective_sha256(tampered_payload),
    })
    with pytest.raises(ValueError, match='does not match referenced objective evaluations'):
        repository.save_pareto_set(tampered)
