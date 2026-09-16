from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite, sqrt
from typing import Any, Sequence

from .models import ContextCreate


class SpatialEditError(ValueError):
    pass


def snap_scalar(value: float, step_m: float) -> float:
    if not isfinite(value) or not isfinite(step_m) or step_m <= 0:
        raise SpatialEditError('Snap value and step must be finite, with step > 0')
    value_d = Decimal(str(value))
    step_d = Decimal(str(step_m))
    units = (value_d / step_d).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return float(units * step_d)


def normalize_direction(vector: Sequence[float]) -> tuple[float, float, float]:
    if len(vector) != 3 or any(not isfinite(float(value)) for value in vector):
        raise SpatialEditError('Aim direction must contain three finite values')
    x, y, z = (float(value) for value in vector)
    length = sqrt(x * x + y * y + z * z)
    if length <= 1e-12:
        raise SpatialEditError('Aim direction must not be zero length')
    return (x / length, y / length, z / length)


class ContextDraft:
    def __init__(self, project_id: str, source_context: dict[str, Any]) -> None:
        self.project_id = project_id
        self.source_context_id = str(source_context['id'])
        self.source_revision_number = int(source_context['revision_number'])
        initial = deepcopy(source_context['payload'])
        ContextCreate.model_validate(initial)
        self._history: list[dict[str, Any]] = [initial]
        self._index = 0

    @property
    def payload(self) -> dict[str, Any]:
        return deepcopy(self._history[self._index])

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index + 1 < len(self._history)

    @property
    def is_dirty(self) -> bool:
        return self._index != 0

    def _commit(self, candidate: dict[str, Any]) -> None:
        try:
            ContextCreate.model_validate(candidate)
        except ValueError as exc:
            raise SpatialEditError(str(exc)) from exc
        self._history = self._history[: self._index + 1]
        self._history.append(candidate)
        self._index += 1

    def undo(self) -> bool:
        if not self.can_undo:
            return False
        self._index -= 1
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self._index += 1
        return True

    def _entity_position_ref(self, payload: dict[str, Any], entity_id: str) -> dict[str, Any]:
        point = payload['measurement_point']
        if point['point_id'] == entity_id:
            return point['position']
        for speaker in payload.get('speakers', []):
            if speaker['speaker_id'] == entity_id:
                if speaker.get('position') is None:
                    raise SpatialEditError(f'{entity_id} has no baseline position')
                return speaker['position']
        raise SpatialEditError(f'Unknown spatial entity: {entity_id}')

    def move_entity(self, entity_id: str, xyz_m: Sequence[float], *, snap_m: float) -> None:
        if len(xyz_m) != 3:
            raise SpatialEditError('Entity position requires X, Y and Z')
        candidate = self.payload
        position = self._entity_position_ref(candidate, entity_id)
        x, y, z = (snap_scalar(float(value), snap_m) for value in xyz_m)
        position.update({'x_m': x, 'y_m': y, 'z_m': z})
        self._commit(candidate)

    def set_speaker_aim(self, speaker_id: str, direction: Sequence[float]) -> None:
        candidate = self.payload
        for speaker in candidate.get('speakers', []):
            if speaker['speaker_id'] == speaker_id:
                speaker['aim_xyz'] = list(normalize_direction(direction))
                self._commit(candidate)
                return
        raise SpatialEditError(f'Unknown speaker: {speaker_id}')

    def move_room_vertex(self, vertex_id: str, xy_m: Sequence[float], *, snap_m: float) -> None:
        if len(xy_m) != 2:
            raise SpatialEditError('Room vertex requires X and Y')
        candidate = self.payload
        room = candidate['room']
        if room.get('geometry_kind') != 'polygon_prism':
            raise SpatialEditError('Room vertices can only be edited for polygon_prism geometry')
        vertices = room.get('footprint_vertices') or []
        for vertex in vertices:
            if vertex['vertex_id'] == vertex_id:
                vertex['x_m'] = snap_scalar(float(xy_m[0]), snap_m)
                vertex['y_m'] = snap_scalar(float(xy_m[1]), snap_m)
                self._commit(candidate)
                return
        raise SpatialEditError(f'Unknown room vertex: {vertex_id}')

    def set_room_height(self, height_m: float, *, snap_m: float) -> None:
        candidate = self.payload
        candidate['room']['height_m'] = snap_scalar(float(height_m), snap_m)
        self._commit(candidate)

    def payload_for_save(self) -> dict[str, Any]:
        candidate = self.payload
        candidate['parent_context_id'] = self.source_context_id
        try:
            return ContextCreate.model_validate(candidate).model_dump(mode='json')
        except ValueError as exc:
            raise SpatialEditError(str(exc)) from exc
