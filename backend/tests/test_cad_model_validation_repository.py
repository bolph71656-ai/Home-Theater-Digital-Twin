from __future__ import annotations

from types import SimpleNamespace

import pytest

from htdt.cad_constraint_models import CadConstraintSet
from htdt.cad_model_validation import build_model_validation
from htdt.cad_model_validation_repository import CadModelValidationRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, RoomPrism, SceneDocument, SceneEntity, Size3
from htdt.cad_search import build_cad_search_spec
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_search_repository import CadSearchRepository
from htdt.comparison import FrequencyResponse


def _fr(offset: float) -> FrequencyResponse:
    return FrequencyResponse(
        frequency_hz=(20.0, 40.0, 80.0, 160.0),
        level_db=(80.0 + offset, 81.0 + offset, 79.0 + offset, 80.0 + offset),
    )


def _search(tmp_path):
    scene_repo = SceneRepository(tmp_path / 'cad.sqlite3')
    document = SceneDocument(
        document_id='o60-fixture',
        schema_version=2,
        room=RoomPrism(width_m=5.0, depth_m=4.0, height_m=2.4),
        entities=(
            SceneEntity(
                entity_id='fl', kind='speaker', name='FL', speaker_role='FL',
                position=Position3(x_m=1.0, y_m=1.0, z_m=1.0),
                size_m=Size3(x_m=0.2, y_m=0.2, z_m=0.4),
            ),
        ),
    )
    revision = scene_repo.save(document, parent_revision_id=None).revision
    spec, _ = build_cad_search_spec(
        revision,
        CadConstraintSet(document_id=document.document_id, constraints=()),
        (CadSearchAxis(entity_id='fl', axis='x', min_m=1.0, max_m=2.0, step_m=1.0),),
        candidate_limit=10,
    )
    search_repo = CadSearchRepository(scene_repo)
    search_repo.save(spec)
    return scene_repo, search_repo, spec


class _RoomSimEvidence:
    def __init__(self, path, spec, candidate_set_sha256):
        self.path = path
        self.spec = spec
        self.candidate_set_sha256 = candidate_set_sha256

    def get_attempt(self, attempt_id):
        if attempt_id != 'attempt-a':
            return None
        return SimpleNamespace(
            attempt_id=attempt_id,
            batch_run_id='batch-a',
            candidate_id='candidate-a',
            status='completed',
            model_version='rew-fixture',
        )

    def get_batch_spec(self, batch_run_id):
        if batch_run_id != 'batch-a':
            return None
        return SimpleNamespace(
            document_id=self.spec.document_id,
            search_spec_id=self.spec.search_spec_id,
            search_spec_sha256=self.spec.search_spec_sha256,
            candidate_set_sha256=self.candidate_set_sha256,
            model_id='rew-roomsim',
        )


class _MeasurementEvidence:
    def __init__(self, path, candidate_set_sha256, *, linked=True):
        self.path = path
        self.candidate_set_sha256 = candidate_set_sha256
        self.linked = linked

    def get_measurement(self, measurement_id):
        if measurement_id != 'measurement-a':
            return None
        return SimpleNamespace(measurement_id=measurement_id, evidence_type='measured')

    def list_measurement_plans(self, search_spec_id):
        measurement_ids = ('measurement-a',) if self.linked else ('other-measurement',)
        return (
            SimpleNamespace(
                status='measured',
                candidate_id='candidate-a',
                candidate_set_sha256=self.candidate_set_sha256,
                measurement_ids=measurement_ids,
            ),
        )


def _record(spec, candidate_set_sha256):
    return build_model_validation(
        document_id=spec.document_id,
        search_spec_id=spec.search_spec_id,
        search_spec_sha256=spec.search_spec_sha256,
        candidate_set_sha256=candidate_set_sha256,
        model_id='rew-roomsim',
        model_version='rew-fixture',
        samples=(
            ('candidate-a', 'holdout', 'attempt-a', 'measurement-a', _fr(0.0), _fr(0.5)),
        ),
        low_hz=20.0,
        high_hz=160.0,
        max_holdout_rms_db=3.0,
    )


def test_validation_repository_persists_cross_evidence_authority(tmp_path):
    scene_repo, search_repo, spec = _search(tmp_path)
    candidate_set_sha256 = 'a' * 64
    repository = CadModelValidationRepository(
        search_repo,
        _RoomSimEvidence(scene_repo.path, spec, candidate_set_sha256),
        _MeasurementEvidence(scene_repo.path, candidate_set_sha256),
    )
    record = _record(spec, candidate_set_sha256)

    repository.save(record)

    assert repository.get(record.validation_id) == record
    assert repository.list_for_search_spec(spec.search_spec_id) == (record,)


def test_validation_repository_rejects_measurement_not_linked_to_candidate_plan(tmp_path):
    scene_repo, search_repo, spec = _search(tmp_path)
    candidate_set_sha256 = 'b' * 64
    repository = CadModelValidationRepository(
        search_repo,
        _RoomSimEvidence(scene_repo.path, spec, candidate_set_sha256),
        _MeasurementEvidence(scene_repo.path, candidate_set_sha256, linked=False),
    )

    with pytest.raises(ValueError, match='not linked'):
        repository.save(_record(spec, candidate_set_sha256))
