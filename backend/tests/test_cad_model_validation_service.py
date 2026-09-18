from __future__ import annotations

import json
from types import SimpleNamespace

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_model_validation_service import (
    CadModelValidationBuildSpec,
    CadModelValidationService,
    CadValidationCandidateBinding,
    CadValidationObjectiveBinding,
    CadValidationRepeatabilitySpec,
    CadValidationSensitivitySpec,
    CadValidationSeparationSpec,
)
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, RoomPrism, SceneDocument, SceneEntity, Size3
from htdt.cad_search import build_cad_search_spec, generate_cad_candidates
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository
from htdt.cad_validation_metrics import CadApplicabilityCheck
from htdt.optimization_objectives import ObjectiveMetric, ObjectiveVector


def _response_payload(offset: float) -> str:
    return json.dumps({
        'frequency_hz': [20.0, 40.0, 80.0, 160.0],
        'magnitude': [80.0 + offset, 81.0 + offset, 79.0 + offset, 80.0 + offset],
    })


class _RoomSim:
    def __init__(self, path, candidates):
        self.path = path
        self.candidates = {candidate.candidate_id: candidate for candidate in candidates}

    def get_attempt(self, attempt_id):
        candidate_id = attempt_id.removeprefix('pred:')
        if candidate_id not in self.candidates:
            return None
        index = list(self.candidates).index(candidate_id)
        return SimpleNamespace(
            status='completed',
            candidate_id=candidate_id,
            response_json=_response_payload(float(index) * 2.0),
        )


class _Measurements:
    def __init__(self, path, candidate_ids):
        self.path = path
        self.records = {}
        self.datasets = {}
        for index, candidate_id in enumerate(candidate_ids):
            revision_id = f'applied:{candidate_id}'
            self._add(f'meas:{candidate_id}', revision_id, float(index) * 2.0 + 0.2)
        self._add('repeat:1', f'applied:{candidate_ids[0]}', 0.2)
        self._add('repeat:2', f'applied:{candidate_ids[0]}', 0.3)

    def _add(self, measurement_id, revision_id, offset):
        self.records[measurement_id] = SimpleNamespace(scene_revision_id=revision_id)
        response = json.loads(_response_payload(offset))
        self.datasets[measurement_id] = SimpleNamespace(
            frequency_hz=tuple(response['frequency_hz']),
            level_db=tuple(response['magnitude']),
        )

    def get_measurement(self, measurement_id):
        return self.records.get(measurement_id)

    def dataset_for_measurement(self, measurement_id):
        return self.datasets.get(measurement_id)


class _Objectives:
    def __init__(self, path, candidate_ids):
        self.path = path
        self.evaluations = {}
        for index, candidate_id in enumerate(candidate_ids, start=1):
            for prefix, value in (('pred-eval', float(index)), ('meas-eval', float(index) + 0.1)):
                evaluation_id = f'{prefix}:{candidate_id}'
                self.evaluations[evaluation_id] = SimpleNamespace(
                    evaluation_id=evaluation_id,
                    vector=ObjectiveVector(
                        candidate_id=candidate_id,
                        metrics=(
                            ObjectiveMetric(
                                objective_id='response.shape_rms_db',
                                value=value,
                                unit='dB',
                            ),
                        ),
                    ),
                )

    def get_evaluation(self, evaluation_id):
        return self.evaluations.get(evaluation_id)


def test_validation_service_builds_full_record_from_repository_evidence(tmp_path):
    scene_repo = SceneRepository(tmp_path / 'cad.sqlite3')
    document = SceneDocument(
        document_id='o60-service',
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
            ),
        ),
    )
    revision = scene_repo.save(document, parent_revision_id=None).revision
    spec, _ = build_cad_search_spec(
        revision,
        CadConstraintSet(document_id=document.document_id, constraints=()),
        (CadSearchAxis(entity_id='fl', axis='x', min_m=1.0, max_m=1.4, step_m=0.2),),
        candidate_limit=10,
    )
    search_repo = CadSearchRepository(scene_repo)
    search_repo.save(spec)
    page = generate_cad_candidates(scene_repo, spec, limit=10)
    candidates = page.candidates[:3]
    candidate_ids = tuple(candidate.candidate_id for candidate in candidates)

    roomsim = _RoomSim(scene_repo.path, candidates)
    measurements = _Measurements(scene_repo.path, candidate_ids)
    objectives = _Objectives(scene_repo.path, candidate_ids)
    service = CadModelValidationService(search_repo, roomsim, measurements, objectives)

    candidate_bindings = tuple(
        CadValidationCandidateBinding(
            candidate_id=candidate_id,
            split='calibration' if index == 2 else 'holdout',
            prediction_attempt_id=f'pred:{candidate_id}',
            measurement_id=f'meas:{candidate_id}',
            objectives=(
                CadValidationObjectiveBinding(
                    objective_id='response.shape_rms_db',
                    predicted_evaluation_id=f'pred-eval:{candidate_id}',
                    measured_evaluation_id=f'meas-eval:{candidate_id}',
                ),
            ),
        )
        for index, candidate_id in enumerate(candidate_ids)
    )
    build_spec = CadModelValidationBuildSpec(
        search_spec_id=spec.search_spec_id,
        candidate_set_sha256=page.candidate_set_sha256,
        campaign_id='campaign-fixture',
        campaign_sha256='4' * 64,
        model_id='rew-roomsim',
        model_version='fixture-1',
        evidence_scope='owned_room',
        low_hz=20.0,
        high_hz=160.0,
        max_holdout_rms_db=1.0,
        candidates=candidate_bindings,
        sensitivity=(
            CadValidationSensitivitySpec(
                objective_id='response.shape_rms_db',
                candidate_a_id=candidate_ids[0],
                candidate_b_id=candidate_ids[1],
                max_observed_sensitivity_per_m=6.0,
                max_model_error_per_m=1.0,
            ),
        ),
        repeatability=(
            CadValidationRepeatabilitySpec(
                measurement_ids=('repeat:1', 'repeat:2'),
            ),
        ),
        separation=(
            CadValidationSeparationSpec(
                candidate_a_id=candidate_ids[0],
                candidate_b_id=candidate_ids[1],
                measurement_a_id=f'meas:{candidate_ids[0]}',
                measurement_b_id=f'meas:{candidate_ids[1]}',
                repeatability_measurement_ids=('repeat:1', 'repeat:2'),
                min_repeatability_multiple=2.0,
            ),
        ),
        applicability=(
            CadApplicabilityCheck(code='geometry', passed=True, detail='supported'),
            CadApplicabilityCheck(code='band', passed=True, detail='supported'),
            CadApplicabilityCheck(code='routing', passed=True, detail='verified'),
        ),
    )

    record = service.build(build_spec)

    assert record.recommendation_gate == 'eligible'
    assert len(record.trend_checks) == 1
    assert record.trend_checks[0].gate == 'pass'
    assert record.sensitivity_checks[0].gate == 'pass'
    assert record.repeatability_checks[0].rms_floor_db > 0
    assert record.separation_checks[0].gate == 'pass'
