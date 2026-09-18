from __future__ import annotations

from types import SimpleNamespace

import pytest

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_measurement_repository import CadMeasurementRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, RoomPrism, SceneDocument, SceneEntity, Size3
from htdt.cad_search import build_cad_search_spec, generate_cad_candidates
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository
from htdt.cad_validation_campaign import (
    CadValidationCampaignCandidate,
    CadValidationCampaignRepeatability,
    CadValidationCampaignSensitivity,
    CadValidationCampaignSeparation,
    CadValidationTargetResponse,
    build_validation_campaign,
)
from htdt.cad_validation_campaign_repository import CadValidationCampaignRepository


def _fixture(tmp_path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    document = SceneDocument(
        document_id='campaign-fixture',
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
    revision = scene_repository.save(document, parent_revision_id=None).revision
    spec, _ = build_cad_search_spec(
        revision,
        CadConstraintSet(document_id=document.document_id, constraints=()),
        (CadSearchAxis(entity_id='fl', axis='x', min_m=1.0, max_m=1.4, step_m=0.2),),
        candidate_limit=10,
    )
    search_repository = CadSearchRepository(scene_repository)
    search_repository.save(spec)
    page = generate_cad_candidates(scene_repository, spec, limit=10)
    candidate_ids = tuple(candidate.candidate_id for candidate in page.candidates[:3])
    measurement_repository = CadMeasurementRepository(scene_repository)
    campaign_repository = CadValidationCampaignRepository(
        search_repository,
        measurement_repository,
    )
    return (
        scene_repository,
        search_repository,
        measurement_repository,
        campaign_repository,
        spec,
        page,
        candidate_ids,
    )


def _campaign(
    spec,
    page,
    candidate_ids,
    *,
    search_spec_sha256: str | None = None,
    candidate_set_sha256: str | None = None,
):
    return build_validation_campaign(
        document_id=spec.document_id,
        search_spec_id=spec.search_spec_id,
        search_spec_sha256=search_spec_sha256 or spec.search_spec_sha256,
        candidate_set_sha256=candidate_set_sha256 or page.candidate_set_sha256,
        model_id='rew-roomsim',
        model_version='5.40',
        requested_band_hz=(20.0, 160.0),
        max_holdout_rms_db=4.0,
        candidates=(
            CadValidationCampaignCandidate(candidate_id=candidate_ids[0], split='holdout'),
            CadValidationCampaignCandidate(candidate_id=candidate_ids[1], split='holdout'),
            CadValidationCampaignCandidate(candidate_id=candidate_ids[2], split='calibration'),
        ),
        objective_ids=('response.shape_rms_db',),
        target_response=CadValidationTargetResponse(
            frequency_hz=(20.0, 40.0, 80.0, 160.0),
            level_db=(0.0, 0.0, 0.0, 0.0),
        ),
        reference_band_hz=(20.0, 160.0),
        sensitivity=(
            CadValidationCampaignSensitivity(
                objective_id='response.shape_rms_db',
                candidate_a_id=candidate_ids[0],
                candidate_b_id=candidate_ids[1],
                max_observed_sensitivity_per_m=20.0,
                max_model_error_per_m=10.0,
            ),
        ),
        repeatability=(
            CadValidationCampaignRepeatability(
                candidate_id=candidate_ids[0],
                min_measurements=2,
            ),
        ),
        separation=(
            CadValidationCampaignSeparation(
                candidate_a_id=candidate_ids[0],
                candidate_b_id=candidate_ids[1],
                repeatability_candidate_id=candidate_ids[0],
                min_repeatability_multiple=2.0,
            ),
        ),
        required_applicability_codes=('geometry', 'band', 'routing'),
    )


def test_campaign_round_trip_preregisters_split_and_thresholds(tmp_path):
    (
        _scene,
        _search,
        _measurement,
        repository,
        spec,
        page,
        candidate_ids,
    ) = _fixture(tmp_path)
    campaign = _campaign(spec, page, candidate_ids)

    repository.save(campaign)

    assert repository.get(campaign.campaign_id) == campaign
    assert repository.find_by_sha(spec.search_spec_id, campaign.campaign_sha256) == campaign
    assert repository.list_for_search_spec(spec.search_spec_id) == (campaign,)
    assert [item.split for item in campaign.candidates] == [
        'holdout',
        'holdout',
        'calibration',
    ]



def test_campaign_rejects_search_spec_hash_mismatch(tmp_path):
    (
        _scene,
        _search,
        _measurement,
        repository,
        spec,
        page,
        candidate_ids,
    ) = _fixture(tmp_path)
    campaign = _campaign(
        spec,
        page,
        candidate_ids,
        search_spec_sha256='f' * 64,
    )

    with pytest.raises(ValueError, match='SearchSpec hash mismatch'):
        repository.save(campaign)


def test_campaign_rejects_candidate_set_hash_mismatch(tmp_path):
    (
        _scene,
        _search,
        _measurement,
        repository,
        spec,
        page,
        candidate_ids,
    ) = _fixture(tmp_path)
    campaign = _campaign(
        spec,
        page,
        candidate_ids,
        candidate_set_sha256='e' * 64,
    )

    with pytest.raises(ValueError, match='candidate-set hash mismatch'):
        repository.save(campaign)


def test_campaign_rejects_candidate_outside_exact_search_set(tmp_path):
    (
        _scene,
        _search,
        _measurement,
        repository,
        spec,
        page,
        candidate_ids,
    ) = _fixture(tmp_path)
    campaign = build_validation_campaign(
        document_id=spec.document_id,
        search_spec_id=spec.search_spec_id,
        search_spec_sha256=spec.search_spec_sha256,
        candidate_set_sha256=page.candidate_set_sha256,
        model_id='rew-roomsim',
        model_version='5.40',
        requested_band_hz=(20.0, 160.0),
        max_holdout_rms_db=4.0,
        candidates=(
            CadValidationCampaignCandidate(candidate_id=candidate_ids[0], split='holdout'),
            CadValidationCampaignCandidate(candidate_id=candidate_ids[1], split='holdout'),
            CadValidationCampaignCandidate(candidate_id='not-a-candidate', split='calibration'),
        ),
        objective_ids=('response.shape_rms_db',),
        target_response=CadValidationTargetResponse(
            frequency_hz=(20.0, 40.0, 80.0, 160.0),
            level_db=(0.0, 0.0, 0.0, 0.0),
        ),
        reference_band_hz=(20.0, 160.0),
        sensitivity=(
            CadValidationCampaignSensitivity(
                objective_id='response.shape_rms_db',
                candidate_a_id=candidate_ids[0],
                candidate_b_id=candidate_ids[1],
                max_observed_sensitivity_per_m=20.0,
                max_model_error_per_m=10.0,
            ),
        ),
        repeatability=(
            CadValidationCampaignRepeatability(candidate_id=candidate_ids[0]),
        ),
        separation=(
            CadValidationCampaignSeparation(
                candidate_a_id=candidate_ids[0],
                candidate_b_id=candidate_ids[1],
                repeatability_candidate_id=candidate_ids[0],
                min_repeatability_multiple=2.0,
            ),
        ),
        required_applicability_codes=('geometry',),
    )

    with pytest.raises(ValueError, match='outside SearchSpec'):
        repository.save(campaign)


def test_campaign_cannot_be_registered_after_candidate_plan_is_measured(tmp_path, monkeypatch):
    (
        _scene,
        _search,
        measurement_repository,
        repository,
        spec,
        page,
        candidate_ids,
    ) = _fixture(tmp_path)
    campaign = _campaign(spec, page, candidate_ids)
    measured_plan = SimpleNamespace(
        status='measured',
        candidate_id=candidate_ids[0],
    )
    monkeypatch.setattr(
        measurement_repository,
        'latest_measurement_plans',
        lambda _search_spec_id: (measured_plan,),
    )

    with pytest.raises(ValueError, match='preregistered before candidate measurement'):
        repository.save(campaign)


def test_campaign_requires_two_holdout_candidates():
    with pytest.raises(ValueError, match='at least two holdout'):
        build_validation_campaign(
            document_id='doc',
            search_spec_id='spec',
            search_spec_sha256='1' * 64,
            candidate_set_sha256='2' * 64,
            model_id='rew-roomsim',
            model_version='5.40',
            requested_band_hz=(20.0, 160.0),
            max_holdout_rms_db=4.0,
            candidates=(
                CadValidationCampaignCandidate(candidate_id='a', split='holdout'),
                CadValidationCampaignCandidate(candidate_id='b', split='calibration'),
            ),
            objective_ids=('response.shape_rms_db',),
            target_response=CadValidationTargetResponse(
                frequency_hz=(20.0, 40.0, 80.0, 160.0),
                level_db=(0.0, 0.0, 0.0, 0.0),
            ),
            reference_band_hz=(20.0, 160.0),
            sensitivity=(
                CadValidationCampaignSensitivity(
                    objective_id='response.shape_rms_db',
                    candidate_a_id='a',
                    candidate_b_id='b',
                    max_observed_sensitivity_per_m=20.0,
                    max_model_error_per_m=10.0,
                ),
            ),
            repeatability=(
                CadValidationCampaignRepeatability(candidate_id='a'),
            ),
            separation=(
                CadValidationCampaignSeparation(
                    candidate_a_id='a',
                    candidate_b_id='b',
                    repeatability_candidate_id='a',
                    min_repeatability_multiple=2.0,
                ),
            ),
            required_applicability_codes=('geometry',),
        )
