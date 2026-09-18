from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_measurement_repository import CadMeasurementRepository
from .cad_objective_models import CadObjectiveInputRef
from .cad_repository import SceneRepository
from .cad_search_repository import CadSearchRepository


class CadMeasurementPlan(BaseModel):
    """Immutable O50 link from one generated candidate to the revision that was physically applied."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    search_spec_id: str = Field(min_length=1)
    search_spec_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_id: str = Field(min_length=1)
    candidate_set_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    applied_scene_revision_id: str = Field(min_length=1)
    applied_scene_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    status: Literal['planned', 'measured'] = 'planned'
    measurement_ids: tuple[str, ...] = ()
    plan_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def validate_status(self) -> 'CadMeasurementPlan':
        if self.status == 'planned' and self.measurement_ids:
            raise ValueError('planned measurement plan cannot contain measurements')
        if self.status == 'measured' and not self.measurement_ids:
            raise ValueError('measured measurement plan requires measurements')
        if len(self.measurement_ids) != len(set(self.measurement_ids)):
            raise ValueError('measurement ids must be unique')
        if self.plan_sha256 != _hash(self.identity_payload()):
            raise ValueError('measurement plan identity hash mismatch')
        return self

    def identity_payload(self) -> dict:
        return {
            'document_id': self.document_id,
            'search_spec_id': self.search_spec_id,
            'search_spec_sha256': self.search_spec_sha256,
            'candidate_id': self.candidate_id,
            'candidate_set_sha256': self.candidate_set_sha256,
            'applied_scene_revision_id': self.applied_scene_revision_id,
            'applied_scene_content_hash': self.applied_scene_content_hash,
            'status': self.status,
            'measurement_ids': list(self.measurement_ids),
        }


def _hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return sha256(raw).hexdigest()


def build_measurement_plan(scene_repository: SceneRepository, search_repository: CadSearchRepository, *,
    search_spec_id: str, candidate_id: str, applied_scene_revision_id: str) -> CadMeasurementPlan:
    spec = search_repository.get(search_spec_id)
    if spec is None:
        raise ValueError('SearchSpec does not exist')
    revision = scene_repository.get(applied_scene_revision_id)
    if revision is None:
        raise ValueError('applied SceneRevision does not exist')
    if revision.document_id != spec.document_id:
        raise ValueError('applied SceneRevision belongs to another document')
    payload = {
        'document_id': spec.document_id, 'search_spec_id': spec.search_spec_id,
        'search_spec_sha256': spec.search_spec_sha256, 'candidate_id': candidate_id,
        'candidate_set_sha256': spec.candidate_set_sha256,
        'applied_scene_revision_id': revision.revision_id,
        'applied_scene_content_hash': revision.content_hash, 'status': 'planned', 'measurement_ids': [],
    }
    return CadMeasurementPlan(plan_id=str(uuid4()), plan_sha256=_hash(payload), **payload)


def complete_measurement_plan(plan: CadMeasurementPlan, measurement_repository: CadMeasurementRepository,
    measurement_ids: tuple[str, ...]) -> CadMeasurementPlan:
    if plan.status != 'planned':
        raise ValueError('measurement plan is already completed')
    if not measurement_ids:
        raise ValueError('at least one measurement is required')
    for measurement_id in measurement_ids:
        record = measurement_repository.get_measurement(measurement_id)
        if record is None:
            raise ValueError(f'measurement does not exist: {measurement_id}')
        if record.document_id != plan.document_id or record.scene_revision_id != plan.applied_scene_revision_id:
            raise ValueError('measurement is not bound to the applied candidate SceneRevision')
        if record.scene_content_hash != plan.applied_scene_content_hash:
            raise ValueError('measurement content hash does not match applied candidate revision')
        if record.evidence_type != 'measured':
            raise ValueError('measurement plan accepts measured evidence only')
    payload = plan.identity_payload()
    payload['status'] = 'measured'
    payload['measurement_ids'] = list(measurement_ids)
    return plan.model_copy(update={'status':'measured','measurement_ids':measurement_ids,'plan_sha256':_hash(payload)})


def measured_input_refs(plan: CadMeasurementPlan) -> tuple[CadObjectiveInputRef, ...]:
    if plan.status != 'measured':
        raise ValueError('measurement plan is not completed')
    return tuple(CadObjectiveInputRef(evidence_class='measured', source_kind='cad_measurement',
        source_id=measurement_id) for measurement_id in plan.measurement_ids)
