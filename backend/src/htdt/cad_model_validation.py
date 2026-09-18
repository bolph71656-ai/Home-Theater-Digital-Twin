from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .comparison import FrequencyResponse, compare_frequency_responses


VALIDATION_ALGORITHM_VERSION = 'model-validation-1'


def _canon(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return sha256(_canon(value).encode('utf-8')).hexdigest()


class CadValidationPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    split: Literal['calibration', 'holdout']
    prediction_source_id: str = Field(min_length=1)
    measurement_id: str = Field(min_length=1)
    rms_difference_db: float = Field(ge=0)
    shape_rms_db: float | None = Field(default=None, ge=0)


class CadModelValidationRecord(BaseModel):
    """Immutable O60 residual validation bound to exact search/evidence authority.

    Passing the residual threshold is deliberately not enough to enable automatic
    recommendations. O60 still requires trend/rank, sensitivity and repeatability
    evidence before O70 may be enabled.
    """

    model_config = ConfigDict(frozen=True)

    validation_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    search_spec_id: str = Field(min_length=1)
    search_spec_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_set_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    requested_band_hz: tuple[float, float]
    pairs: tuple[CadValidationPair, ...] = Field(min_length=1)
    holdout_rms_db: float | None = Field(default=None, ge=0)
    calibration_rms_db: float | None = Field(default=None, ge=0)
    max_holdout_rms_db: float = Field(gt=0)
    residual_gate: Literal['pass', 'fail', 'insufficient']
    recommendation_gate: Literal['disabled'] = 'disabled'
    gate_reasons: tuple[str, ...]
    algorithm_version: Literal['model-validation-1'] = VALIDATION_ALGORITHM_VERSION
    created_at_utc: str = Field(min_length=1)
    validation_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_identity(self) -> 'CadModelValidationRecord':
        low_hz, high_hz = self.requested_band_hz
        if low_hz <= 0 or high_hz <= low_hz:
            raise ValueError('model validation frequency band is invalid')

        split_by_candidate: dict[str, str] = {}
        for pair in self.pairs:
            prior = split_by_candidate.setdefault(pair.candidate_id, pair.split)
            if prior != pair.split:
                raise ValueError('candidate cannot appear in both calibration and holdout splits')
        identities = {
            (pair.prediction_source_id, pair.measurement_id)
            for pair in self.pairs
        }
        if len(identities) != len(self.pairs):
            raise ValueError('validation prediction/measurement pairs must be unique')

        if self.holdout_rms_db is None and self.residual_gate != 'insufficient':
            raise ValueError('missing holdout evidence requires residual_gate=insufficient')
        if self.holdout_rms_db is not None:
            expected = 'pass' if self.holdout_rms_db <= self.max_holdout_rms_db else 'fail'
            if self.residual_gate != expected:
                raise ValueError('residual gate does not match holdout RMS threshold')

        if self.validation_sha256 != _hash(self.identity_payload()):
            raise ValueError('model validation identity hash mismatch')
        return self

    def identity_payload(self) -> dict[str, Any]:
        return {
            'document_id': self.document_id,
            'search_spec_id': self.search_spec_id,
            'search_spec_sha256': self.search_spec_sha256,
            'candidate_set_sha256': self.candidate_set_sha256,
            'model_id': self.model_id,
            'model_version': self.model_version,
            'requested_band_hz': list(self.requested_band_hz),
            'pairs': [pair.model_dump(mode='json') for pair in self.pairs],
            'holdout_rms_db': self.holdout_rms_db,
            'calibration_rms_db': self.calibration_rms_db,
            'max_holdout_rms_db': self.max_holdout_rms_db,
            'residual_gate': self.residual_gate,
            'recommendation_gate': self.recommendation_gate,
            'gate_reasons': list(self.gate_reasons),
            'algorithm_version': self.algorithm_version,
        }


def build_model_validation(
    *,
    document_id: str,
    search_spec_id: str,
    search_spec_sha256: str,
    candidate_set_sha256: str,
    model_id: str,
    model_version: str,
    samples: tuple[
        tuple[
            str,
            Literal['calibration', 'holdout'],
            str,
            str,
            FrequencyResponse,
            FrequencyResponse,
        ],
        ...,
    ],
    low_hz: float,
    high_hz: float,
    max_holdout_rms_db: float,
) -> CadModelValidationRecord:
    pairs: list[CadValidationPair] = []
    buckets: dict[str, list[float]] = {'calibration': [], 'holdout': []}

    for candidate_id, split, prediction_id, measurement_id, predicted, measured in samples:
        result = compare_frequency_responses(predicted, measured, low_hz, high_hz)
        if result.rms_difference_db is None:
            raise ValueError('validation pair has insufficient overlapping response data')
        pair = CadValidationPair(
            candidate_id=candidate_id,
            split=split,
            prediction_source_id=prediction_id,
            measurement_id=measurement_id,
            rms_difference_db=result.rms_difference_db,
            shape_rms_db=result.shape_rms_db,
        )
        pairs.append(pair)
        buckets[split].append(result.rms_difference_db)

    def aggregate_rms(values: list[float]) -> float | None:
        if not values:
            return None
        return (sum(value * value for value in values) / len(values)) ** 0.5

    calibration_rms = aggregate_rms(buckets['calibration'])
    holdout_rms = aggregate_rms(buckets['holdout'])
    if holdout_rms is None:
        residual_gate = 'insufficient'
        residual_reason = 'holdout evidence is required'
    elif holdout_rms > max_holdout_rms_db:
        residual_gate = 'fail'
        residual_reason = (
            f'holdout RMS {holdout_rms:.3f} dB exceeds '
            f'{max_holdout_rms_db:.3f} dB gate'
        )
    else:
        residual_gate = 'pass'
        residual_reason = 'holdout residual threshold passed'

    gate_reasons = (
        residual_reason,
        'automatic recommendation remains disabled until O60 trend/rank, '
        'sensitivity and repeatability checks are independently satisfied',
    )
    payload = {
        'document_id': document_id,
        'search_spec_id': search_spec_id,
        'search_spec_sha256': search_spec_sha256,
        'candidate_set_sha256': candidate_set_sha256,
        'model_id': model_id,
        'model_version': model_version,
        'requested_band_hz': (float(low_hz), float(high_hz)),
        'pairs': tuple(pairs),
        'holdout_rms_db': holdout_rms,
        'calibration_rms_db': calibration_rms,
        'max_holdout_rms_db': float(max_holdout_rms_db),
        'residual_gate': residual_gate,
        'recommendation_gate': 'disabled',
        'gate_reasons': gate_reasons,
        'algorithm_version': VALIDATION_ALGORITHM_VERSION,
    }
    provisional = CadModelValidationRecord.model_construct(
        validation_id=str(uuid4()),
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        validation_sha256='0' * 64,
        **payload,
    )
    return CadModelValidationRecord(
        **provisional.model_dump(exclude={'validation_sha256'}),
        validation_sha256=_hash(provisional.identity_payload()),
    )
