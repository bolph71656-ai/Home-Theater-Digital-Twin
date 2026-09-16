from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


EvidenceType = Literal['measured', 'derived', 'predicted', 'unknown']
RadiationScope = Literal['single', 'bass_managed', 'mixed', 'unknown']


class Point3D(BaseModel):
    x_m: float
    y_m: float
    z_m: float


class SpeakerPlacement(BaseModel):
    speaker_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    model: str | None = None
    position: Point3D | None = None
    aim_xyz: tuple[float, float, float] | None = None
    mounting_type: str | None = None


class RoomSnapshot(BaseModel):
    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    geometry_kind: Literal['rectangular', 'reference_box'] = 'rectangular'
    notes: str | None = None


class MeasurementPoint(BaseModel):
    point_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    position: Point3D
    aim_xyz: tuple[float, float, float] | None = None
    position_precision_m: float | None = Field(default=None, ge=0)


class AVRConfiguration(BaseModel):
    manufacturer: str = 'Yamaha'
    model: str = 'RX-A4A'
    firmware: str | None = None
    input_name: str | None = None
    volume_db: float | None = None
    processing_mode: str | None = None
    peq_mode: str | None = None
    extra: dict[str, str | float | int | bool | None] = Field(default_factory=dict)


class ContextCreate(BaseModel):
    room: RoomSnapshot
    speakers: list[SpeakerPlacement]
    measurement_point: MeasurementPoint
    avr: AVRConfiguration = Field(default_factory=AVRConfiguration)
    notes: str | None = None
    parent_context_id: str | None = None

    @model_validator(mode='after')
    def validate_positions(self) -> 'ContextCreate':
        room = self.room
        positions: list[tuple[str, Point3D]] = [('measurement point', self.measurement_point.position)]
        positions.extend((speaker.speaker_id, speaker.position) for speaker in self.speakers if speaker.position is not None)
        for label, point in positions:
            if not (0 <= point.x_m <= room.width_m and 0 <= point.y_m <= room.depth_m and 0 <= point.z_m <= room.height_m):
                raise ValueError(f'{label} is outside the room reference bounds')
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ImportPreviewRequest(BaseModel):
    filename: str = Field(min_length=1)
    raw_base64: str = Field(min_length=1)


class MeasurementImportRequest(ImportPreviewRequest):
    context_id: str
    channel_role: str = Field(min_length=1)
    evidence_type: EvidenceType = 'unknown'
    source_speaker_ids: list[str] = Field(default_factory=list)
    radiation_scope: RadiationScope = 'unknown'
    captured_at: str | None = None
    notes: str | None = None


class ExcludedBand(BaseModel):
    low_hz: float = Field(gt=0)
    high_hz: float = Field(gt=0)

    @model_validator(mode='after')
    def validate_order(self) -> 'ExcludedBand':
        if self.high_hz <= self.low_hz:
            raise ValueError('high_hz must be greater than low_hz')
        return self


class ComparisonCreate(BaseModel):
    dataset_a_id: str
    dataset_b_id: str
    low_hz: float = Field(gt=0)
    high_hz: float = Field(gt=0)
    reference_low_hz: float | None = Field(default=None, gt=0)
    reference_high_hz: float | None = Field(default=None, gt=0)
    excluded_bands: list[ExcludedBand] = Field(default_factory=list)
    label: str | None = None

    @model_validator(mode='after')
    def validate_bands(self) -> 'ComparisonCreate':
        if self.high_hz <= self.low_hz:
            raise ValueError('high_hz must be greater than low_hz')
        if (self.reference_low_hz is None) != (self.reference_high_hz is None):
            raise ValueError('reference band requires both bounds')
        if self.reference_low_hz is not None and self.reference_high_hz is not None:
            if self.reference_high_hz <= self.reference_low_hz:
                raise ValueError('reference_high_hz must be greater than reference_low_hz')
        return self


class BackupRestoreRequest(BaseModel):
    archive_base64: str = Field(min_length=1)
