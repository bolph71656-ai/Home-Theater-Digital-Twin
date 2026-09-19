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


def test_o90b_multidimensional_sampling_is_reproducible_and_linked(tmp_path) -> None:
    from htdt.optimization_robustness import LinkedPerturbationGroup
    from htdt.optimization_robustness_multidimensional import (
        build_multidimensional_sampling_plan,
        derive_multidimensional_robustness_spec,
    )

    _revision, _constraints, _search_spec, _nominal, base_spec = _fixture(tmp_path)
    linked = LinkedPerturbationGroup(
        group_id='front-listener-x',
        axis_multipliers={
            'speaker-x': 1.0,
            'listener-x': -0.5,
        },
    )

    spec_a = derive_multidimensional_robustness_spec(
        base_spec,
        sample_count=8,
        seed=1701,
        linked_groups=(linked,),
        created_at_utc='2026-09-19T00:02:00+00:00',
    )
    spec_b = derive_multidimensional_robustness_spec(
        base_spec,
        sample_count=8,
        seed=1701,
        linked_groups=(linked,),
        created_at_utc='2026-09-19T00:02:00+00:00',
    )
    assert spec_a == spec_b
    assert spec_a.parent_robustness_spec_id == base_spec.robustness_spec_id
    assert (
        spec_a.parent_robustness_spec_sha256
        == base_spec.robustness_spec_sha256
    )

    plans_a = build_multidimensional_sampling_plan(spec_a)
    plans_b = build_multidimensional_sampling_plan(spec_b)
    assert plans_a == plans_b
    assert len(plans_a) == 8
    assert plans_a[0].step == 'nominal'
    assert all(
        item.step == 'multidimensional'
        for item in plans_a[1:]
    )
    assert all(
        set(item.parameter_deltas) == {axis.axis_id for axis in spec_a.axes}
        for item in plans_a[1:]
    )

    linked_plan = plans_a[3]
    speaker_norm = linked_plan.parameter_deltas['speaker-x'] / 0.02
    listener_norm = linked_plan.parameter_deltas['listener-x'] / 0.05
    assert listener_norm == pytest.approx(-0.5 * speaker_norm)


def test_o90b_keeps_infeasible_samples_builds_envelope_and_round_trips(
    tmp_path,
    monkeypatch,
) -> None:
    from htdt.cad_robustness_repository import CadRobustnessRepository
    from htdt.cad_search_models import CadCandidate
    from htdt.optimization_objectives import ObjectiveMetric, ObjectiveVector
    from htdt.optimization_robustness import (
        PerturbationObjectiveResult,
        build_robustness_spec,
    )
    import htdt.optimization_robustness_multidimensional as o90b

    revision, constraints, search_spec, nominal, original = _fixture(tmp_path)
    axes = tuple(
        axis.model_copy(update={'allowed_min': 0.99})
        if axis.axis_id == 'speaker-x'
        else axis
        for axis in original.axes
        if axis.axis_id in {'speaker-x', 'listener-x'}
    )
    base_spec = build_robustness_spec(
        source_revision=revision,
        search_spec=search_spec,
        candidate=CadCandidate.model_validate_json(original.candidate_payload_json),
        candidate_set_sha256=original.candidate_set_sha256,
        nominal_objective=nominal,
        nominal_prediction_result_ref=original.nominal_prediction_result_ref,
        model_id=original.model_id,
        model_version=original.model_version,
        prediction_provider_id=original.prediction_provider_id,
        fidelity=original.fidelity,
        axes=axes,
        software_version='test',
        created_at_utc='2026-09-19T00:00:00+00:00',
    )
    spec = o90b.derive_multidimensional_robustness_spec(
        base_spec,
        sample_count=7,
        seed=9,
        created_at_utc='2026-09-19T00:02:00+00:00',
    )

    calls = {'g10': 0, 'o80': 0}
    real_g10 = o90b.evaluate_cad_constraints
    real_o80 = o90b.orientation_constraint_rejections

    def counted_g10(*args, **kwargs):
        calls['g10'] += 1
        return real_g10(*args, **kwargs)

    def counted_o80(*args, **kwargs):
        calls['o80'] += 1
        return real_o80(*args, **kwargs)

    monkeypatch.setattr(o90b, 'evaluate_cad_constraints', counted_g10)
    monkeypatch.setattr(o90b, 'orientation_constraint_rejections', counted_o80)

    def evaluator(document, sample_id: str) -> PerturbationObjectiveResult:
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

    samples, evaluations = o90b.evaluate_multidimensional_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=evaluator,
        created_at_utc='2026-09-19T00:03:00+00:00',
    )

    assert calls == {'g10': len(samples), 'o80': len(samples)}
    assert len(samples) == spec.sample_count
    assert samples[1].step == 'multidimensional'
    assert not samples[1].feasible
    assert '__uncertainty_bound__:speaker-x:min' in samples[1].domain_rejection_ids
    assert samples[1].objective_vector is None

    evaluation = evaluations[0]
    assert evaluation.sampled_worst_semantics == 'sampled_worst'
    assert samples[1].sample_id in evaluation.infeasible_sample_ids
    assert evaluation.feasible_fraction == pytest.approx(
        sum(1 for item in samples if item.feasible) / len(samples)
    )
    assert evaluation.sampled_envelope is not None
    assert evaluation.sampled_envelope.percentile_values is None
    assert evaluation.percentile_semantics == 'not_available_bounded_interval'
    assert evaluation.mean_value is None
    assert evaluation.constraint_violation_probability is None
    assert evaluation.probability_semantics is None
    assert evaluation.sampling_provenance_sha256 is not None

    repository = CadRobustnessRepository(tmp_path / 'o90b.sqlite3')
    repository.save_spec(spec)
    repository.save_samples(samples)
    repository.save_evaluations(evaluations)
    assert repository.get_spec(spec.robustness_spec_id) == spec
    assert repository.list_samples(spec.robustness_spec_id) == samples
    assert repository.list_evaluations(spec.robustness_spec_id) == evaluations


def test_o90b_uses_o40_for_separate_nominal_and_sampled_worst_pareto() -> None:
    from htdt.optimization_objectives import ObjectiveMetric, ObjectiveVector
    from htdt.optimization_robustness import (
        RobustnessEvaluation,
        SampledObjectiveEnvelope,
        canonical_robustness_sha256,
    )
    from htdt.optimization_robustness_multidimensional import (
        RobustParetoSelection,
        robust_pareto_front,
    )

    objective_id = 'response.shape_rms_db'

    def evaluation(candidate_id: str, nominal: float, sampled_worst: float):
        envelope = SampledObjectiveEnvelope(
            sampled_min_sample_id=f'{candidate_id}-s0',
            sampled_min_value=min(nominal, sampled_worst),
            sampled_max_sample_id=f'{candidate_id}-s0',
            sampled_max_value=max(nominal, sampled_worst),
            percentile_values=None,
        )
        identity = {
            'schema_version': 1,
            'robustness_spec_id': f'rob-{candidate_id}',
            'robustness_spec_sha256': '1' * 64,
            'candidate_id': candidate_id,
            'objective_id': objective_id,
            'objective_unit': 'dB',
            'direction': 'minimize',
            'nominal_sample_id': f'{candidate_id}-s0',
            'nominal_value': nominal,
            'local_sensitivities': [],
            'sampled_worst_semantics': 'sampled_worst',
            'sampled_worst_sample_id': f'{candidate_id}-s0',
            'sampled_worst_value': sampled_worst,
            'sample_ids': [f'{candidate_id}-s0'],
            'infeasible_sample_ids': [],
            'failed_sample_ids': [],
            'sampled_envelope': envelope.model_dump(mode='json'),
            'feasible_fraction': 1.0,
            'sampling_provenance_sha256': '2' * 64,
            'percentile_semantics': 'not_available_bounded_interval',
        }
        digest = canonical_robustness_sha256(identity)
        return RobustnessEvaluation(
            **identity,
            evaluation_id=f're-{digest[:24]}',
            evaluation_sha256=digest,
            created_at_utc='2026-09-19T00:04:00+00:00',
        )

    nominal_a = ObjectiveVector(
        candidate_id='a',
        metrics=(
            ObjectiveMetric(objective_id=objective_id, value=1.0, unit='dB'),
        ),
    )
    nominal_b = ObjectiveVector(
        candidate_id='b',
        metrics=(
            ObjectiveMetric(objective_id=objective_id, value=2.0, unit='dB'),
        ),
    )
    selection = RobustParetoSelection(
        nominal_objective_ids=(objective_id,),
        robustness_objective_ids=(objective_id,),
    )
    result = robust_pareto_front(
        (
            (nominal_a, (evaluation('a', 1.0, 4.0),)),
            (nominal_b, (evaluation('b', 2.0, 2.0),)),
        ),
        selection,
    )

    assert result.objective_ids == (
        f'nominal::{objective_id}',
        f'robust.sampled_worst::{objective_id}',
    )
    assert result.non_dominated_candidate_ids == ('a', 'b')
    assert result.dominated_by == {'a': (), 'b': ()}


def test_o90b_requires_nominal_and_both_corner_anchors(tmp_path) -> None:
    from htdt.optimization_robustness_multidimensional import (
        derive_multidimensional_robustness_spec,
    )

    _revision, _constraints, _search_spec, _nominal, base_spec = _fixture(tmp_path)

    with pytest.raises(ValueError, match='at least three samples'):
        derive_multidimensional_robustness_spec(
            base_spec,
            sample_count=2,
            seed=1,
            created_at_utc='2026-09-19T00:02:00+00:00',
        )



def _o90b_distribution_model(base_spec):
    from htdt.optimization_robustness import (
        DistributionAxisUncertainty,
        DistributionUncertaintyModel,
    )

    return DistributionUncertaintyModel(
        model_id='known-uniform-inputs',
        axes=tuple(
            DistributionAxisUncertainty(
                axis_id=axis.axis_id,
                distribution='uniform',
                min_delta=-float(axis.minus_delta),
                max_delta=float(axis.plus_delta),
            )
            for axis in base_spec.axes
        ),
    )


def _o90b_linear_evaluator(document, sample_id: str) -> PerturbationObjectiveResult:
    speaker = document.entity('speaker-fl')
    value = 2.0 + (speaker.position.x_m - 1.0) * 10.0
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


def test_o90b_explicit_distribution_recovers_known_mean_and_percentile(
    tmp_path,
) -> None:
    from htdt.optimization_robustness_uncertainty import (
        build_uncertainty_sampling_plan,
        derive_uncertainty_robustness_spec,
        evaluate_uncertainty_robustness,
    )

    revision, constraints, search_spec, nominal, base_spec = _fixture(tmp_path)
    model = _o90b_distribution_model(base_spec)
    spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        sample_count=65,
        seed=1701,
        created_at_utc='2026-09-19T00:10:00+00:00',
    )
    replay_spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        sample_count=65,
        seed=1701,
        created_at_utc='2026-09-19T00:10:01+00:00',
    )
    changed_seed_spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        sample_count=65,
        seed=1702,
        created_at_utc='2026-09-19T00:10:01+00:00',
    )
    assert replay_spec.robustness_spec_id == spec.robustness_spec_id
    assert replay_spec.robustness_spec_sha256 == spec.robustness_spec_sha256
    assert build_uncertainty_sampling_plan(replay_spec) == (
        build_uncertainty_sampling_plan(spec)
    )
    assert changed_seed_spec.robustness_spec_sha256 != spec.robustness_spec_sha256
    assert tuple(
        item.sample_id for item in build_uncertainty_sampling_plan(changed_seed_spec)
    ) != tuple(item.sample_id for item in build_uncertainty_sampling_plan(spec))

    result = evaluate_uncertainty_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=_o90b_linear_evaluator,
        created_at_utc='2026-09-19T00:11:00+00:00',
    )

    assert result.status == 'completed'
    evaluation = result.evaluations[0]
    assert evaluation.probability_semantics == 'explicit_distribution'
    assert evaluation.percentile_semantics == 'explicit_probability_model'
    assert evaluation.mean_value == pytest.approx(2.0, abs=1e-12)
    assert evaluation.sampled_envelope is not None
    assert evaluation.sampled_envelope.percentile_values is not None
    assert evaluation.sampled_envelope.percentile_values['p95'] == pytest.approx(
        2.18,
        abs=0.005,
    )
    assert evaluation.constraint_violation_probability == pytest.approx(0.0)
    assert evaluation.feasible_fraction == pytest.approx(1.0)


def test_o90b_empirical_samples_remain_non_probabilistic_without_weights(
    tmp_path,
) -> None:
    from htdt.optimization_robustness import (
        EmpiricalUncertaintyModel,
        ExplicitPerturbationState,
    )
    from htdt.optimization_robustness_uncertainty import (
        build_uncertainty_sampling_plan,
        derive_uncertainty_robustness_spec,
        evaluate_uncertainty_robustness,
    )

    revision, constraints, search_spec, nominal, base_spec = _fixture(tmp_path)
    model = EmpiricalUncertaintyModel(
        model_id='installation-observations',
        samples=(
            ExplicitPerturbationState(
                state_id='z-observation',
                parameter_deltas={'speaker-x': 0.01},
            ),
            ExplicitPerturbationState(
                state_id='a-observation',
                parameter_deltas={'speaker-x': -0.01},
            ),
        ),
    )
    spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        created_at_utc='2026-09-19T00:12:00+00:00',
    )
    plans = build_uncertainty_sampling_plan(spec)
    assert [item.uncertainty_item_id for item in plans[1:]] == [
        'a-observation',
        'z-observation',
    ]
    assert all(item.probability_weight is None for item in plans[1:])

    result = evaluate_uncertainty_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=_o90b_linear_evaluator,
        created_at_utc='2026-09-19T00:13:00+00:00',
    )
    evaluation = result.evaluations[0]
    assert evaluation.percentile_semantics == 'not_available_empirical_unweighted'
    assert evaluation.sampled_envelope is not None
    assert evaluation.sampled_envelope.percentile_values is None
    assert evaluation.mean_value is None
    assert evaluation.constraint_violation_probability is None
    assert evaluation.probability_semantics is None


def test_o90b_explicit_discrete_weights_produce_violation_probability(
    tmp_path,
) -> None:
    from htdt.cad_search_models import CadCandidate
    from htdt.optimization_robustness import (
        DiscreteUncertaintyModel,
        ExplicitPerturbationState,
        build_robustness_spec,
    )
    from htdt.optimization_robustness_uncertainty import (
        derive_uncertainty_robustness_spec,
        evaluate_uncertainty_robustness,
    )

    revision, constraints, search_spec, nominal, original = _fixture(tmp_path)
    axes = tuple(
        axis.model_copy(update={'allowed_min': 0.99})
        if axis.axis_id == 'speaker-x'
        else axis
        for axis in original.axes
    )
    base_spec = build_robustness_spec(
        source_revision=revision,
        search_spec=search_spec,
        candidate=CadCandidate.model_validate_json(original.candidate_payload_json),
        candidate_set_sha256=original.candidate_set_sha256,
        nominal_objective=nominal,
        nominal_prediction_result_ref=original.nominal_prediction_result_ref,
        model_id=original.model_id,
        model_version=original.model_version,
        prediction_provider_id=original.prediction_provider_id,
        fidelity=original.fidelity,
        axes=axes,
        software_version='test',
        created_at_utc='2026-09-19T00:14:00+00:00',
    )
    model = DiscreteUncertaintyModel(
        model_id='mounting-alternatives',
        states=(
            ExplicitPerturbationState(
                state_id='negative',
                parameter_deltas={'speaker-x': -0.02},
                probability_weight=0.25,
            ),
            ExplicitPerturbationState(
                state_id='positive',
                parameter_deltas={'speaker-x': 0.01},
                probability_weight=0.75,
            ),
        ),
    )
    spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        created_at_utc='2026-09-19T00:15:00+00:00',
    )

    result = evaluate_uncertainty_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=_o90b_linear_evaluator,
        created_at_utc='2026-09-19T00:16:00+00:00',
    )
    evaluation = result.evaluations[0]
    assert evaluation.probability_semantics == 'explicit_discrete_weights'
    assert evaluation.constraint_violation_probability == pytest.approx(0.25)
    assert evaluation.feasible_fraction == pytest.approx(0.5)
    assert evaluation.feasible_fraction != pytest.approx(
        1.0 - evaluation.constraint_violation_probability
    )
    assert any(not sample.feasible for sample in result.samples[1:])


def test_o90b_cancel_cache_resume_and_stale_reuse_protection(tmp_path) -> None:
    from htdt.optimization_robustness_uncertainty import (
        derive_uncertainty_robustness_spec,
        evaluate_uncertainty_robustness,
    )

    revision, constraints, search_spec, nominal, base_spec = _fixture(tmp_path)
    model = _o90b_distribution_model(base_spec)
    spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        sample_count=9,
        seed=77,
        created_at_utc='2026-09-19T00:17:00+00:00',
    )
    repository = CadRobustnessRepository(tmp_path / 'o90b-resume.sqlite3')
    cancel_calls = {'count': 0}

    def cancel_after_one_perturbation() -> bool:
        cancel_calls['count'] += 1
        return cancel_calls['count'] > 2

    cancelled = evaluate_uncertainty_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=_o90b_linear_evaluator,
        cache=repository,
        cancel_requested=cancel_after_one_perturbation,
        created_at_utc='2026-09-19T00:18:00+00:00',
    )
    assert cancelled.status == 'cancelled'
    assert len(cancelled.samples) == 2
    assert repository.list_samples(spec.robustness_spec_id) == cancelled.samples

    resumed = evaluate_uncertainty_robustness(
        source_revision=revision,
        search_spec=search_spec,
        spec=spec,
        constraint_set=constraints,
        nominal_objective=nominal,
        evaluator=_o90b_linear_evaluator,
        cache=repository,
        created_at_utc='2026-09-19T00:18:00+00:00',
    )
    assert resumed.status == 'completed'
    assert resumed.reused_sample_ids == tuple(
        sample.sample_id for sample in cancelled.samples
    )
    assert len(resumed.computed_sample_ids) == spec.sample_count - len(cancelled.samples)
    assert repository.get_spec(spec.robustness_spec_id) == spec
    assert repository.list_samples(spec.robustness_spec_id) == resumed.samples
    assert repository.list_evaluations(spec.robustness_spec_id) == resumed.evaluations

    changed_spec = derive_uncertainty_robustness_spec(
        base_spec,
        uncertainty_model=model,
        sample_count=9,
        seed=78,
        created_at_utc='2026-09-19T00:19:00+00:00',
    )
    with pytest.raises(ValueError, match='stale or incompatible'):
        evaluate_uncertainty_robustness(
            source_revision=revision,
            search_spec=search_spec,
            spec=changed_spec,
            constraint_set=constraints,
            nominal_objective=nominal,
            evaluator=_o90b_linear_evaluator,
            completed_samples=resumed.samples,
            created_at_utc='2026-09-19T00:20:00+00:00',
        )

    changed_revision = revision.model_copy(
        update={'revision_id': f'{revision.revision_id}-changed'}
    )
    with pytest.raises(ValueError, match='SceneRevision authority mismatch'):
        evaluate_uncertainty_robustness(
            source_revision=changed_revision,
            search_spec=search_spec,
            spec=spec,
            constraint_set=constraints,
            nominal_objective=nominal,
            evaluator=_o90b_linear_evaluator,
            created_at_utc='2026-09-19T00:20:00+00:00',
        )
