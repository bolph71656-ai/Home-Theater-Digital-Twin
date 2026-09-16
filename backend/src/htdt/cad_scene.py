from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite, sqrt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SceneValidationError(ValueError):
    pass


class Position3(BaseModel):
    model_config = ConfigDict(frozen=True)
    x_m: float
    y_m: float
    z_m: float

    @field_validator('x_m', 'y_m', 'z_m')
    @classmethod
    def finite(cls, value: float) -> float:
        value = float(value)
        if not isfinite(value):
            raise ValueError('position values must be finite')
        return value


class Direction3(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: float
    y: float
    z: float

    @model_validator(mode='after')
    def normalized(self) -> 'Direction3':
        values = (float(self.x), float(self.y), float(self.z))
        if any(not isfinite(value) for value in values):
            raise ValueError('direction values must be finite')
        length = sqrt(sum(value * value for value in values))
        if length <= 1e-12:
            raise ValueError('direction must not be zero length')
        if abs(length - 1.0) > 1e-6:
            raise ValueError('direction must be normalized')
        return self


class Size3(BaseModel):
    model_config = ConfigDict(frozen=True)
    x_m: float = Field(gt=0)
    y_m: float = Field(gt=0)
    z_m: float = Field(gt=0)


class RoomPrism(BaseModel):
    model_config = ConfigDict(frozen=True)
    room_id: str = 'room'
    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    height_m: float = Field(gt=0)


class SceneEntity(BaseModel):
    model_config = ConfigDict(frozen=True)
    entity_id: str = Field(min_length=1)
    kind: Literal['speaker', 'measurement_point', 'furniture']
    name: str = Field(min_length=1)
    position: Position3
    size_m: Size3 | None = None
    speaker_role: str | None = None
    aim_xyz: Direction3 | None = None

    @model_validator(mode='after')
    def semantic_fields(self) -> 'SceneEntity':
        if self.kind == 'speaker' and not self.speaker_role:
            raise ValueError('speaker_role is required for speakers')
        if self.kind != 'speaker' and (self.speaker_role is not None or self.aim_xyz is not None):
            raise ValueError('speaker fields are only valid for speakers')
        return self


class SceneDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    document_id: str = Field(min_length=1)
    schema_version: int = 1
    coordinate_system: Literal['htdt-x-right-y-rear-z-up-m'] = 'htdt-x-right-y-rear-z-up-m'
    room: RoomPrism
    entities: tuple[SceneEntity, ...]

    @model_validator(mode='after')
    def unique_entities(self) -> 'SceneDocument':
        ids = [entity.entity_id for entity in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError('entity_id values must be unique')
        return self

    def entity(self, entity_id: str) -> SceneEntity:
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity
        raise KeyError(entity_id)


def canonical_scene_json(document: SceneDocument) -> str:
    return json.dumps(
        document.model_dump(mode='json'),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def scene_content_hash(document: SceneDocument) -> str:
    return sha256(canonical_scene_json(document).encode('utf-8')).hexdigest()


def domain_to_render(position: Position3) -> tuple[float, float, float]:
    """Map HTDT +X right/+Y rear/+Z up into VTK's right-handed world."""
    return (position.x_m, -position.y_m, position.z_m)


def render_delta_to_domain(delta_xyz: tuple[float, float, float], base: Position3) -> Position3:
    dx, dy, dz = (float(value) for value in delta_xyz)
    return Position3(x_m=base.x_m + dx, y_m=base.y_m - dy, z_m=base.z_m + dz)


F1_DOCUMENT_ID = 'fixture-f1'


def make_f1_scene() -> SceneDocument:
    return SceneDocument(
        document_id=F1_DOCUMENT_ID,
        room=RoomPrism(width_m=6.0, depth_m=4.0, height_m=2.4),
        entities=(
            SceneEntity(
                entity_id='speaker-fl',
                kind='speaker',
                name='Front Left',
                speaker_role='FL',
                position=Position3(x_m=1.35, y_m=0.75, z_m=1.05),
                size_m=Size3(x_m=0.24, y_m=0.28, z_m=0.42),
                aim_xyz=None,
            ),
            SceneEntity(
                entity_id='speaker-c',
                kind='speaker',
                name='Center',
                speaker_role='C',
                position=Position3(x_m=3.0, y_m=0.55, z_m=0.85),
                size_m=Size3(x_m=0.50, y_m=0.28, z_m=0.20),
                aim_xyz=None,
            ),
            SceneEntity(
                entity_id='speaker-fr',
                kind='speaker',
                name='Front Right',
                speaker_role='FR',
                position=Position3(x_m=4.65, y_m=0.75, z_m=1.05),
                size_m=Size3(x_m=0.24, y_m=0.28, z_m=0.42),
                aim_xyz=Direction3(x=-0.514496, y=0.857493, z=0.0),
            ),
            SceneEntity(
                entity_id='point-mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=3.0, y_m=3.0, z_m=1.1),
            ),
            SceneEntity(
                entity_id='furniture-left',
                kind='furniture',
                name='Left cabinet',
                position=Position3(x_m=0.55, y_m=2.2, z_m=0.45),
                size_m=Size3(x_m=0.8, y_m=0.45, z_m=0.9),
            ),
        ),
    )
