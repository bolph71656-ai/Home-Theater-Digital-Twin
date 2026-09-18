from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .comparison import FrequencyResponse, compare_frequency_responses


VALIDATION_ALGORITHM_VERSION = 'model-validation-1'


def _canon(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value: object) -> str:
    return sha256(_canon(value).encode()).hexdigest()


class CadValidationPair(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate_id: str = Field(min_length=1)
    split: Literal['calibration', 'holdout']
    prediction_source_id: str = Field(min_length=1)
    measurement_id: str = Field(min_length=1)
    rms_difference_db: float = Field(ge=0)
    shape_rms_db: float | None = Field(default=None, ge=0)


class CadModelValidationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    validation_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    requested_band_hz: tuple[float, float]
    pairs: tuple[CadValidationPair, ...] = Field(min_length=1)
    holdout_rms_db: float | None = Field(default=None, ge=0)
    calibration_rms_db: float | None = Field(default=None, ge=0)
    recommendation_gate: Literal['disabled', 'eligible']
    gate_reasons: tuple[str, ...]
    algorithm_version: Literal['model-validation-1'] = VALIDATION_ALGORITHM_VERSION
    created_at_utc: str = Field(min_length=1)
    validation_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_identity(self):
        if not any(pair.split == 'holdout' for pair in self.pairs) and self.recommendation_gate == 'eligible':
            raise ValueError('recommendation cannot be eligible without holdout evidence')
        if self.validation_sha256 != _hash(self.identity_payload()):
            raise ValueError('model validation identity hash mismatch')
        return self

    def identity_payload(self):
        return {
            'model_id': self.model_id, 'model_version': self.model_version,
            'requested_band_hz': list(self.requested_band_hz),
            'pairs': [pair.model_dump(mode='json') for pair in self.pairs],
            'holdout_rms_db': self.holdout_rms_db, 'calibration_rms_db': self.calibration_rms_db,
            'recommendation_gate': self.recommendation_gate, 'gate_reasons': list(self.gate_reasons),
            'algorithm_version': self.algorithm_version,
        }


def build_model_validation(*, model_id: str, model_version: str,
    samples: tuple[tuple[str, Literal['calibration','holdout'], str, str, FrequencyResponse, FrequencyResponse], ...],
    low_hz: float, high_hz: float, max_holdout_rms_db: float) -> CadModelValidationRecord:
    pairs=[]; buckets={'calibration':[], 'holdout':[]}
    for candidate_id, split, prediction_id, measurement_id, predicted, measured in samples:
        result=compare_frequency_responses(predicted, measured, low_hz, high_hz)
        if result.rms_difference_db is None:
            raise ValueError('validation pair has insufficient overlapping response data')
        pair=CadValidationPair(candidate_id=candidate_id, split=split, prediction_source_id=prediction_id,
            measurement_id=measurement_id, rms_difference_db=result.rms_difference_db,
            shape_rms_db=result.shape_rms_db)
        pairs.append(pair); buckets[split].append(result.rms_difference_db)
    def rms(values):
        return None if not values else (sum(v*v for v in values)/len(values))**0.5
    cal=rms(buckets['calibration']); hold=rms(buckets['holdout'])
    reasons=[]
    if hold is None: reasons.append('holdout evidence is required')
    elif hold > max_holdout_rms_db: reasons.append(f'holdout RMS {hold:.3f} dB exceeds {max_holdout_rms_db:.3f} dB gate')
    gate='eligible' if not reasons else 'disabled'
    payload={'model_id':model_id,'model_version':model_version,'requested_band_hz':(low_hz,high_hz),
        'pairs':tuple(pairs),'holdout_rms_db':hold,'calibration_rms_db':cal,
        'recommendation_gate':gate,'gate_reasons':tuple(reasons),'algorithm_version':VALIDATION_ALGORITHM_VERSION}
    provisional = CadModelValidationRecord.model_construct(
        validation_id=str(uuid4()), created_at_utc=datetime.now(timezone.utc).isoformat(),
        validation_sha256='0' * 64, **payload
    )
    return CadModelValidationRecord(
        **provisional.model_dump(exclude={'validation_sha256'}),
        validation_sha256=_hash(provisional.identity_payload()),
    )
