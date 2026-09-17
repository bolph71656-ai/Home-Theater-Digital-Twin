from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cad_scene import Direction3, Position3


MeasurementEvidenceType = Literal['measured', 'derived', 'predicted', 'unknown']
MeasurementSourceKind = Literal['rew_api', 'rew_text', 'unknown']
MeasurementPhaseStatus = Literal['valid', 'absent', 'unknown']
RadiationScope = Literal['single', 'bass_managed', 'mixed', 'unknown']
RoutingEvidence = Literal['verified', 'manual', 'inferred', 'unknown']


class CadMeasurementRecord(BaseModel):
    """Immutable evidence binding to one exact native SceneRevision."""

    model_config = ConfigDict(frozen=True)

    measurement_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    scene_revision_id: str = Field(min_length=1)
    scene_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    measurement_entity_id: str = Field(min_length=1)
    measurement_position: Position3
    measurement_direction: Direction3 | None = None

    evidence_type: MeasurementEvidenceType = 'unknown'
    channel_role: str = 'unknown'
    source_speaker_ids: tuple[str, ...] = ()
    radiation_scope: RadiationScope = 'unknown'
    routing_evidence: RoutingEvidence = 'unknown'

    captured_at: str | None = None
    imported_at: str = Field(min_length=1)
    source_kind: MeasurementSourceKind
    external_source_id: str | None = None

    quality_status: str = 'unknown'
    quality_reasons: tuple[str, ...] = ()
    quality_source: str = 'unknown'
    provenance_json: str = '{}'

    @field_validator('source_speaker_ids')
    @classmethod
    def unique_source_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError('source_speaker_ids must be unique')
        if any(not item for item in value):
            raise ValueError('source_speaker_ids must not contain empty values')
        return value


class CadFrequencyResponseDataset(BaseModel):
    """Immutable frequency-response samples on their original imported grid."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str = Field(min_length=1)
    measurement_id: str = Field(min_length=1)
    frequency_hz: tuple[float, ...]
    level_db: tuple[float, ...]
    phase_deg: tuple[float, ...] | None = None
    phase_status: MeasurementPhaseStatus
    level_reference: str = 'unknown'
    smoothing: str | None = None
    processing_json: str = '{}'
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    importer_version: str = Field(min_length=1)

    @model_validator(mode='after')
    def valid_arrays(self) -> 'CadFrequencyResponseDataset':
        count = len(self.frequency_hz)
        if count < 2:
            raise ValueError('frequency response requires at least two samples')
        if len(self.level_db) != count:
            raise ValueError('frequency and level arrays must have equal length')
        if self.phase_deg is not None and len(self.phase_deg) != count:
            raise ValueError('phase array length must match frequency array')
        if self.phase_status == 'absent' and self.phase_deg is not None:
            raise ValueError('phase_status absent requires phase_deg=None')
        if self.phase_status == 'valid' and self.phase_deg is None:
            raise ValueError('phase_status valid requires phase data')
        previous = 0.0
        for index, frequency in enumerate(self.frequency_hz):
            frequency = float(frequency)
            if not isfinite(frequency) or frequency <= 0:
                raise ValueError('frequency values must be finite and positive')
            if index and frequency <= previous:
                raise ValueError('frequency values must be strictly increasing')
            previous = frequency
        if any(not isfinite(float(value)) for value in self.level_db):
            raise ValueError('level values must be finite')
        if self.phase_deg is not None and any(not isfinite(float(value)) for value in self.phase_deg):
            raise ValueError('phase values must be finite')
        return self
