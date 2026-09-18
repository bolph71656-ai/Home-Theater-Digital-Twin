from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Literal, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_objective_models import canonical_objective_json, canonical_objective_sha256


CAMPAIGN_SCHEMA_VERSION = 1


class CadValidationCampaignCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    split: Literal['calibration', 'holdout']


class CadValidationCampaignSensitivity(BaseModel):
    model_config = ConfigDict(frozen=True)

    objective_id: str = Field(min_length=1)
    candidate_a_id: str = Field(min_length=1)
    candidate_b_id: str = Field(min_length=1)
    max_observed_sensitivity_per_m: float = Field(gt=0)
    max_model_error_per_m: float = Field(gt=0)


class CadValidationCampaignRepeatability(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    min_measurements: int = Field(default=2, ge=2)
    reference_band_hz: tuple[float, float] | None = None

    @model_validator(mode='after')
    def valid_band(self) -> 'CadValidationCampaignRepeatability':
        if self.reference_band_hz is not None:
            low, high = self.reference_band_hz
            if low <= 0 or high <= low:
                raise ValueError('repeatability reference band is invalid')
        return self


class CadValidationCampaignSeparation(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_a_id: str = Field(min_length=1)
    candidate_b_id: str = Field(min_length=1)
    repeatability_candidate_id: str = Field(min_length=1)
    min_repeatability_multiple: float = Field(gt=0)


class CadValidationCampaign(BaseModel):
    """Immutable preregistration for a real owned-room O60 study."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = CAMPAIGN_SCHEMA_VERSION
    campaign_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    search_spec_id: str = Field(min_length=1)
    search_spec_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_set_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)

    requested_band_hz: tuple[float, float]
    max_holdout_rms_db: float = Field(gt=0)

    candidates: tuple[CadValidationCampaignCandidate, ...] = Field(min_length=2)
    objective_ids: tuple[str, ...] = Field(min_length=1)
    objective_evaluation_spec_json: str = Field(min_length=2)
    objective_evaluation_spec_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    trend_tolerance_by_objective: dict[str, float] = Field(default_factory=dict)
    trend_min_comparable_pairs: int = Field(default=1, ge=1)
    trend_min_agreement_ratio: float = Field(default=0.75, ge=0, le=1)

    sensitivity: tuple[CadValidationCampaignSensitivity, ...] = Field(min_length=1)
    repeatability: tuple[CadValidationCampaignRepeatability, ...] = Field(min_length=1)
    separation: tuple[CadValidationCampaignSeparation, ...] = Field(min_length=1)
    required_applicability_codes: tuple[str, ...] = Field(min_length=1)

    created_at_utc: str = Field(min_length=1)
    campaign_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_identity(self) -> 'CadValidationCampaign':
        low, high = self.requested_band_hz
        if low <= 0 or high <= low:
            raise ValueError('validation campaign frequency band is invalid')

        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError('validation campaign candidate ids must be unique')
        split_by_candidate = {item.candidate_id: item.split for item in self.candidates}
        if 'calibration' not in split_by_candidate.values():
            raise ValueError('validation campaign requires calibration candidates')
        holdout_ids = [
            candidate_id
            for candidate_id, split in split_by_candidate.items()
            if split == 'holdout'
        ]
        if len(holdout_ids) < 2:
            raise ValueError('validation campaign requires at least two holdout candidates')

        if len(self.objective_ids) != len(set(self.objective_ids)):
            raise ValueError('validation campaign objective ids must be unique')
        if any(value < 0 for value in self.trend_tolerance_by_objective.values()):
            raise ValueError('validation campaign trend tolerances must be non-negative')
        if not set(self.trend_tolerance_by_objective).issubset(self.objective_ids):
            raise ValueError('trend tolerance references an objective outside the campaign')

        try:
            evaluation_spec = json.loads(self.objective_evaluation_spec_json)
        except json.JSONDecodeError as exc:
            raise ValueError('campaign objective evaluation spec must contain JSON') from exc
        if canonical_objective_json(evaluation_spec) != self.objective_evaluation_spec_json:
            raise ValueError('campaign objective evaluation spec must be canonical JSON')
        if canonical_objective_sha256(evaluation_spec) != self.objective_evaluation_spec_sha256:
            raise ValueError('campaign objective evaluation spec hash mismatch')
        if isinstance(evaluation_spec, dict) and 'objectives' in evaluation_spec:
            if tuple(evaluation_spec['objectives']) != self.objective_ids:
                raise ValueError('campaign objective ids do not match evaluation spec')

        sensitivity_keys: set[tuple[str, tuple[str, str]]] = set()
        for requirement in self.sensitivity:
            if requirement.objective_id not in self.objective_ids:
                raise ValueError('campaign sensitivity references an unknown objective')
            pair = tuple(sorted((requirement.candidate_a_id, requirement.candidate_b_id)))
            if pair[0] == pair[1]:
                raise ValueError('campaign sensitivity requires two candidates')
            if not set(pair).issubset(split_by_candidate):
                raise ValueError('campaign sensitivity references an unknown candidate')
            if any(split_by_candidate[item] != 'holdout' for item in pair):
                raise ValueError('campaign sensitivity requires holdout candidates')
            key = (requirement.objective_id, pair)
            if key in sensitivity_keys:
                raise ValueError('campaign sensitivity requirements must be unique')
            sensitivity_keys.add(key)

        repeatability_ids = [item.candidate_id for item in self.repeatability]
        if len(repeatability_ids) != len(set(repeatability_ids)):
            raise ValueError('campaign repeatability candidates must be unique')
        if not set(repeatability_ids).issubset(split_by_candidate):
            raise ValueError('campaign repeatability references an unknown candidate')

        separation_keys: set[tuple[str, str]] = set()
        for requirement in self.separation:
            if requirement.candidate_a_id == requirement.candidate_b_id:
                raise ValueError('campaign candidate separation requires two candidates')
            if not {
                requirement.candidate_a_id,
                requirement.candidate_b_id,
                requirement.repeatability_candidate_id,
            }.issubset(split_by_candidate):
                raise ValueError('campaign candidate separation references an unknown candidate')
            if requirement.repeatability_candidate_id not in repeatability_ids:
                raise ValueError(
                    'campaign candidate separation requires a preregistered repeatability candidate'
                )
            key = tuple(sorted((requirement.candidate_a_id, requirement.candidate_b_id)))
            if key in separation_keys:
                raise ValueError('campaign candidate separation requirements must be unique')
            separation_keys.add(key)

        codes = self.required_applicability_codes
        if len(codes) != len(set(codes)) or any(not code for code in codes):
            raise ValueError('campaign applicability codes must be unique non-empty values')

        if self.campaign_sha256 != canonical_objective_sha256(self.identity_payload()):
            raise ValueError('validation campaign identity hash mismatch')
        return self

    def identity_payload(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'document_id': self.document_id,
            'search_spec_id': self.search_spec_id,
            'search_spec_sha256': self.search_spec_sha256,
            'candidate_set_sha256': self.candidate_set_sha256,
            'model_id': self.model_id,
            'model_version': self.model_version,
            'requested_band_hz': list(self.requested_band_hz),
            'max_holdout_rms_db': self.max_holdout_rms_db,
            'candidates': [item.model_dump(mode='json') for item in self.candidates],
            'objective_ids': list(self.objective_ids),
            'objective_evaluation_spec': json.loads(self.objective_evaluation_spec_json),
            'objective_evaluation_spec_sha256': self.objective_evaluation_spec_sha256,
            'trend_tolerance_by_objective': dict(sorted(self.trend_tolerance_by_objective.items())),
            'trend_min_comparable_pairs': self.trend_min_comparable_pairs,
            'trend_min_agreement_ratio': self.trend_min_agreement_ratio,
            'sensitivity': [item.model_dump(mode='json') for item in self.sensitivity],
            'repeatability': [item.model_dump(mode='json') for item in self.repeatability],
            'separation': [item.model_dump(mode='json') for item in self.separation],
            'required_applicability_codes': list(self.required_applicability_codes),
        }


def build_validation_campaign(
    *,
    document_id: str,
    search_spec_id: str,
    search_spec_sha256: str,
    candidate_set_sha256: str,
    model_id: str,
    model_version: str,
    requested_band_hz: tuple[float, float],
    max_holdout_rms_db: float,
    candidates: Sequence[CadValidationCampaignCandidate],
    objective_ids: Sequence[str],
    objective_evaluation_spec: Any,
    trend_tolerance_by_objective: Mapping[str, float] | None = None,
    trend_min_comparable_pairs: int = 1,
    trend_min_agreement_ratio: float = 0.75,
    sensitivity: Sequence[CadValidationCampaignSensitivity] = (),
    repeatability: Sequence[CadValidationCampaignRepeatability] = (),
    separation: Sequence[CadValidationCampaignSeparation] = (),
    required_applicability_codes: Sequence[str] = (),
) -> CadValidationCampaign:
    spec_json = canonical_objective_json(objective_evaluation_spec)
    spec_sha = canonical_objective_sha256(objective_evaluation_spec)
    payload = {
        'document_id': document_id,
        'search_spec_id': search_spec_id,
        'search_spec_sha256': search_spec_sha256,
        'candidate_set_sha256': candidate_set_sha256,
        'model_id': model_id,
        'model_version': model_version,
        'requested_band_hz': tuple(float(value) for value in requested_band_hz),
        'max_holdout_rms_db': float(max_holdout_rms_db),
        'candidates': tuple(candidates),
        'objective_ids': tuple(objective_ids),
        'objective_evaluation_spec_json': spec_json,
        'objective_evaluation_spec_sha256': spec_sha,
        'trend_tolerance_by_objective': dict(trend_tolerance_by_objective or {}),
        'trend_min_comparable_pairs': trend_min_comparable_pairs,
        'trend_min_agreement_ratio': trend_min_agreement_ratio,
        'sensitivity': tuple(sensitivity),
        'repeatability': tuple(repeatability),
        'separation': tuple(separation),
        'required_applicability_codes': tuple(required_applicability_codes),
    }
    provisional = CadValidationCampaign.model_construct(
        campaign_id=str(uuid4()),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        campaign_sha256='0' * 64,
        **payload,
    )
    return CadValidationCampaign(
        **provisional.model_dump(exclude={'campaign_sha256'}),
        campaign_sha256=canonical_objective_sha256(provisional.identity_payload()),
    )
