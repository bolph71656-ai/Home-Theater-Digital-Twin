from __future__ import annotations

import pytest

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_objective_models import CadObjectiveInputRef
from htdt.cad_objectives import build_objective_evaluation
from htdt.cad_repository import SceneRepository
from htdt.cad_robustness_repository import CadRobustnessRepository
from htdt.cad_scene import (
    Direction3,
    Position3,
    RoomPrism,
    SceneDocument,
    SceneEntity,
    Size3,
)
from htdt.cad_search import build_cad_search_spec, generate_cad_candidates
from htdt.cad_search_models import CadCandidate, CadSearchAxis
from htdt.optimization_objectives import ObjectiveMetric, ObjectiveVector
from htdt.optimization_robustness import (
    PerturbationObjectiveResult,
    UncertaintyAxis,
    build_local_stencil,
    build_robustness_spec,
    evaluate_local_robustness,
)


DOCUMENT_ID = 'o90a-fixture'


def _scene() -> SceneDocument:
    return SceneDocument(
        document_id=DOCUMENT_ID,
        schema_version=3,
        room=RoomPrism(width_m=6.0, depth_m=4.0, height_m=2.4),
        entities=(
            SceneEntity(
                entity_id='speaker-fl',
                kind='speaker',
                name='FL',
                position=Position3(x_m=1.0, y_m=1.0, z_m=1.0),
                size_m=Size3(x_m=0.22, y_m=0.28, z_m=0.42),
                speaker_role='FL',
                aim_xyz=Direction3(x=0.0, y=1.0, z=0.0),
            ),
            SceneEntity(
                entity_id='listener-main',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=3.0, y_m=3.0, z_m=1.1),
            ),
        ),
    )


def _fixture(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision = scene_repository.save(_scene(), parent_revision_id=None).revision
    constraints = CadConstraintSet(document_id=DOCUMENT_ID, constraints=())
    search_spec, _ = build_cad_search_spec(
        revision,
        constraints,
        (
            CadSearchAxis(
                entity_id='speaker-fl',
                axis='x',
                min_m=1.0,
                max_m=1.0,
                step_m=0.1,
            ),
        ),
        candidate_limit=10,
        name='O90A exact candidate',
    )
    page = generate_cad_candidates(scene_repository, search_spec)
    candidate = page.candidates[0]
    prediction_ref = f'prediction:{candidate.candidate_id}'
    nominal = build_objective_evaluation(
        revision,
        search_spec,
        candidate.candidate_id,
        ObjectiveVector(
            candidate_id=candidate.candidate_id,
            metrics=(
                ObjectiveMetric(
                    objective_id='response.shape_rms_db',
                    value=2.0,
                    unit='dB',
                ),
            ),
        ),
        evaluation_spec={
            'algorithm_version': 'objective-vector-1',
            'objectives': ['response.shape_rms_db'],
        },
        input_refs=(
            CadObjectiveInputRef(
                evidence_class='derived',
                source_kind='candidate_geometry',
                source_id=candidate.candidate_id,
            ),
            CadObjectiveInputRef(
                evidence_class='predicted',
                source_kind='prediction_fixture',
                source_id=prediction_ref,
            ),
        ),
    )
    axes = (
        UncertaintyAxis(
            axis_id='speaker-x',
            entity_id='speaker-fl',
            parameter='speaker_x_m',
            unit='m',
            nominal_value=1.0,
            minus_delta=0.02,
            plus_delta=0.02,
        ),
        UncertaintyAxis(
            axis_id='listener-x',
            entity_id='listener-main',
            parameter='listener_x_m',
            unit='m',
            nominal_value=3.0,
            minus_delta=0.05,
            plus_delta=0.05,
        ),
        UncertaintyAxis(
            axis_id='aim-yaw',
            entity_id='speaker-fl',
            parameter='aim_yaw_deg',
            unit='deg',
            nominal_value=0.0,
            minus_delta=2.0,
            plus_delta=2.0,
        ),
        UncertaintyAxis(
            axis_id='aim-pitch',
            entity_id='speaker-fl',
            parameter='aim_pitch_deg',
            unit='deg',
            nominal_value=0.0,
            minus_delta=1.0,
            plus_delta=1.0,
        ),
        UncertaintyAxis(
            axis_id='body-yaw',
            entity_id='speaker-fl',
            parameter='body_yaw_deg',
            unit='deg',
            nominal_value=0.0,
            minus_delta=2.0,
            plus_delta=2.0,
        ),
    )
    spec = build_robustness_spec(
        source_revision=revision,
        search_spec=search_spec,
        candidate=candidate,
        candidate_set_sha256=page.candidate_set_sha256,
        nominal_objective=nominal,
        nominal_prediction_result_ref=prediction_ref,
        model_id='synthetic-model',
        model_version='1',
        prediction_provider_id='test-provider',
        fidelity='development_synthetic',
        axes=axes,
        software_version='test',
        created_at_utc='2026-09-19T00:00:00+00:00',
    )
    return revision, constraints, search_spec, nominal, spec


def test_o90a_spec_and_local_stencil_are_immutable_and_deterministic(tmp_path) -> None:
    _revision, _constraints, _search_spec, _nominal, spec = _fixture(tmp_path)

    plans = build_local_stencil(spec)

    assert len(plans) == 1 + 2 * len(spec.axes)
    assert plans[0].step == 'nominal'
    assert [item.axis_id for item in plans[1:3]] == ['aim-pitch', 'aim-pitch']
    assert [item.step for item in plans[1:3]] == ['minus', 'plus']
    assert spec.sampling_strategy == 'deterministic_local_stencil'
    assert all(axis.uncertainty_model == 'bounded_interval' for axis in spec.axes)
    with pytest.raises(Exception):
        spec.axes = ()


def test_o90a_rechecks_constraints_keeps_infeasible_sample_and_builds_sensitivity(
    tmp_path,
) -> None:
    revision, constraints, search_spec, nominal, spec = _fixture(tmp_path)
    # Make one declared bounded perturbation infeasible without inventing a
    # probability model. Other axes remain scoreable.
    axes = tuple(
        axis.model_copy(update={'allowed_min': 0.99})
        if axis.axis_id == 'speaker-x'
        else axis
        for axis in spec.axes
    )
    spec = build_robustness_spec(
        source_revision=revision,
        search_spec=search_spec,
        candidate=CadCandidate.model_validate_json(spec.candidate_payload_json),
        candidate_set_sha256=spec.candidate_set_sha256,
        nominal_objective=nominal,
        nominal_prediction_result_ref=spec.nominal_prediction_result_ref,
        model_id=spec.model_id,
        model_version=spec.model_version,
        prediction_provider_id=spec.prediction_provider_id,
        fidelity=spec.fidelity,
        axes=axes,
        software_version='test',
        created_at_utc='2026-09-19T00:00:00+00:00',
    )

    def evaluator(document: SceneDocument, sample_id: str) -> PerturbationObjectiveResult:
        speaker = document.entity('speaker-fl')
        listener = document.entity('listener-main')
        value = (
            2.0
            + abs(speaker.position.x_m - 1.0) * 10.0
            + abs(listener.position.x_m - 3.0) * 2.0
        )
        return PerturbationObjectiveResult(
            prediction_result_ref=f'prediction:{sample_id}',
            objective_vector=ObjectiveVector(
                candidate_id=sample_id,
                metrics=(
                    ObjectiveMetric(
                        objective_id='response.shape_rms_db',
                        value=value,
                        unit='dB',
                    ),
                ),
            ),
        )

    samples, evaluations = evaluate_local_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=evaluator,
        created_at_utc='2026-09-19T00:01:00+00:00',
    )

    infeasible = next(
        item
        for item in samples
        if item.axis_id == 'speaker-x' and item.step == 'minus'
    )
    assert not infeasible.feasible
    assert infeasible.objective_vector is None
    assert infeasible.domain_rejection_ids == (
        '__uncertainty_bound__:speaker-x:min',
    )
    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert evaluation.sampled_worst_semantics == 'sampled_worst'
    assert infeasible.sample_id in evaluation.infeasible_sample_ids
    speaker_sensitivity = next(
        item
        for item in evaluation.local_sensitivities
        if item.axis_id == 'speaker-x'
    )
    assert speaker_sensitivity.state == 'infeasible_or_failed'
    listener_sensitivity = next(
        item
        for item in evaluation.local_sensitivities
        if item.axis_id == 'listener-x'
    )
    assert listener_sensitivity.state == 'available'
    assert listener_sensitivity.central_slope_per_unit == pytest.approx(0.0)


def test_o90a_persistence_round_trips_exact_provenance(tmp_path) -> None:
    revision, constraints, search_spec, nominal, spec = _fixture(tmp_path)

    def evaluator(_document: SceneDocument, sample_id: str) -> PerturbationObjectiveResult:
        return PerturbationObjectiveResult(
            prediction_result_ref=f'prediction:{sample_id}',
            objective_vector=ObjectiveVector(
                candidate_id=sample_id,
                metrics=(
                    ObjectiveMetric(
                        objective_id='response.shape_rms_db',
                        value=2.1,
                        unit='dB',
                    ),
                ),
            ),
        )

    samples, evaluations = evaluate_local_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=evaluator,
        created_at_utc='2026-09-19T00:01:00+00:00',
    )
    repository = CadRobustnessRepository(tmp_path / 'robust.sqlite3')
    repository.save_spec(spec)
    repository.save_samples(samples)
    repository.save_evaluations(evaluations)

    assert repository.get_spec(spec.robustness_spec_id) == spec
    assert repository.list_samples(spec.robustness_spec_id) == samples
    assert repository.list_evaluations(spec.robustness_spec_id) == evaluations
    assert repository.list_specs_for_candidate(
        document_id=spec.document_id,
        scene_revision_id=spec.scene_revision_id,
        candidate_id=spec.candidate_id,
    ) == (spec,)
