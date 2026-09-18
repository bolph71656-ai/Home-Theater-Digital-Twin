from __future__ import annotations

import json

import pytest

from htdt.cad_adaptive_repository import CadAdaptivePlanRepository
from htdt.cad_adaptive_service import CadAdaptivePlannerService
from htdt.cad_extended_search import generate_extended_candidates
from htdt.cad_extended_search_repository import CadExtendedSearchRepository
from htdt.cad_measurement_repository import CadMeasurementRepository
from htdt.cad_model_validation_repository import CadModelValidationRepository
from htdt.cad_objective_repository import CadObjectiveRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_roomsim_repository import CadRoomSimRepository
from htdt.cad_search_repository import CadSearchRepository
from htdt.measurement_editor import measurement_evidence_label, measurement_is_synthetic
from htdt.cad_synthetic_demo import (
    SYNTHETIC_DEMO_DOCUMENT_ID,
    seed_synthetic_optimization_demo,
)


def _repositories(scene_repository):
    search = CadSearchRepository(scene_repository)
    measurements = CadMeasurementRepository(scene_repository)
    roomsim = CadRoomSimRepository(scene_repository, search)
    objectives = CadObjectiveRepository(scene_repository, search)
    validation = CadModelValidationRepository(
        search,
        roomsim,
        measurements,
        objectives,
    )
    adaptive = CadAdaptivePlanRepository(search, validation)
    extended = CadExtendedSearchRepository(search, validation)
    return search, measurements, roomsim, objectives, validation, adaptive, extended


def test_synthetic_demo_persists_o10_through_o80_without_owned_room_promotion(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')

    result = seed_synthetic_optimization_demo(scene_repository)

    assert result.document_id == SYNTHETIC_DEMO_DOCUMENT_ID
    (
        search,
        measurements,
        _roomsim,
        objectives,
        validation_repository,
        adaptive_repository,
        extended_repository,
    ) = _repositories(scene_repository)

    spec = search.get(result.search_spec_id)
    assert spec is not None
    assert spec.document_id == SYNTHETIC_DEMO_DOCUMENT_ID

    record = validation_repository.get(result.validation_id)
    assert record is not None
    assert record.evidence_scope == 'synthetic_fixture'
    assert record.recommendation_gate == 'disabled'
    assert record.gate_reasons == (
        'automatic recommendation requires owned-room evidence',
    )
    assert record.residual_gate == 'pass'
    assert all(check.gate == 'pass' for check in record.trend_checks)
    assert all(check.gate == 'pass' for check in record.sensitivity_checks)
    assert all(check.gate == 'pass' for check in record.separation_checks)
    assert all(check.passed for check in record.applicability_checks)
    assert validation_repository.latest_eligible_for_search_spec(
        result.search_spec_id
    ) is None

    plan = adaptive_repository.get(result.adaptive_plan_id)
    assert plan is not None
    assert plan.execution_scope == 'development_synthetic'
    assert plan.source_evidence_scope == 'synthetic_fixture'
    assert plan.validation_recommendation_gate == 'disabled'
    assert plan.selected_candidate_id == result.adaptive_selected_candidate_id
    assert len(plan.proposals) == 2

    all_measurements = measurements.list_measurements(
        SYNTHETIC_DEMO_DOCUMENT_ID
    )
    assert len(all_measurements) == 5
    for measurement in all_measurements:
        provenance = json.loads(measurement.provenance_json)
        assert provenance['validation_scope'] == 'synthetic_fixture'
        assert provenance['physical_measurement'] is False
        assert measurement_is_synthetic(measurement)
        assert measurement_evidence_label(measurement) == 'Synthetic'

    evaluations = objectives.list_evaluations(result.search_spec_id)
    predicted_candidates = {
        evaluation.candidate_id
        for evaluation in evaluations
        if any(
            ref.evidence_class == 'predicted'
            for ref in evaluation.input_refs
        )
    }
    assert len(predicted_candidates) == 6

    extended_spec = extended_repository.get_spec(result.extended_search_id)
    assert extended_spec is not None
    capability = extended_repository.get_capability(
        extended_spec.capability_id
    )
    assert capability is not None
    assert capability.evidence_scope == 'synthetic_fixture'
    assert capability.validation_id is None
    extended_page = generate_extended_candidates(
        scene_repository,
        spec,
        extended_spec,
        limit=50,
    )
    assert extended_page.feasible_candidate_count == 18
    assert (
        extended_page.candidate_set_sha256
        == result.extended_candidate_set_sha256
    )

    service = CadAdaptivePlannerService(
        search,
        objectives,
        validation_repository,
        adaptive_repository,
    )
    with pytest.raises(
        ValueError,
        match='production adaptive planning requires',
    ):
        service.build_and_save(
            validation_id=result.validation_id,
            execution_scope='production_owned_room',
        )


def test_synthetic_demo_refuses_duplicate_seed_in_same_data_directory(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    seed_synthetic_optimization_demo(scene_repository)

    with pytest.raises(ValueError, match='already exists'):
        seed_synthetic_optimization_demo(scene_repository)
