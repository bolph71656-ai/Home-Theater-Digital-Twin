from __future__ import annotations

from dataclasses import dataclass
from math import floor, hypot, isfinite
from typing import Callable, Literal

from .cad_scene import Position3, SceneDocument, SceneEntity, quaternion_to_matrix3

AxisName = Literal['x', 'y', 'z']
SnapKind = Literal['vertex', 'midpoint', 'edge', 'alignment']
ScreenProjector = Callable[[Position3], tuple[float, float]]

SNAP_PRIORITY: dict[SnapKind, int] = {
    'vertex': 0,
    'midpoint': 1,
    'edge': 2,
    'alignment': 3,
}


@dataclass(frozen=True)
class SnapCandidate:
    stable_id: str
    kind: SnapKind
    entity_id: str
    target: Position3
    screen_anchor: Position3
    axis: AxisName
    label: str

    @property
    def priority(self) -> int:
        return SNAP_PRIORITY[self.kind]


@dataclass(frozen=True)
class SnapSelection:
    candidate: SnapCandidate
    distance_dip: float


class SnapSelector:
    def __init__(self, *, acquire_radius_dip: float = 8.0, retain_radius_dip: float = 12.0) -> None:
        if acquire_radius_dip <= 0 or retain_radius_dip < acquire_radius_dip:
            raise ValueError('snap radii must satisfy 0 < acquire <= retain')
        self.acquire_radius_dip = float(acquire_radius_dip)
        self.retain_radius_dip = float(retain_radius_dip)
        self._retained_id: str | None = None
        self._projection_cache: dict[
            str,
            tuple[tuple[float, float, float], tuple[float, float]],
        ] = {}

    @property
    def retained_id(self) -> str | None:
        return self._retained_id

    def reset(self) -> None:
        self._retained_id = None
        self._projection_cache.clear()

    def _project_candidate(self, candidate: SnapCandidate, project: ScreenProjector) -> tuple[float, float]:
        anchor_key = (
            candidate.screen_anchor.x_m,
            candidate.screen_anchor.y_m,
            candidate.screen_anchor.z_m,
        )
        cached = self._projection_cache.get(candidate.stable_id)
        if cached is not None and cached[0] == anchor_key:
            return cached[1]
        projected = project(candidate.screen_anchor)
        self._projection_cache[candidate.stable_id] = (anchor_key, projected)
        return projected

    def select(
        self,
        candidates: tuple[SnapCandidate, ...],
        probe: Position3,
        project: ScreenProjector,
    ) -> SnapSelection | None:
        probe_screen = project(probe)

        # Hysteresis is the common case while dragging along an acquired feature.
        # Resolve the retained candidate first so stable drags do not score every
        # scene feature on every mouse-move event.
        if self._retained_id is not None:
            retained = next(
                (candidate for candidate in candidates if candidate.stable_id == self._retained_id),
                None,
            )
            if retained is not None:
                distance = _screen_distance(self._project_candidate(retained, project), probe_screen)
                if distance <= self.retain_radius_dip:
                    return SnapSelection(retained, distance)

        best: tuple[tuple[int, float, str], SnapCandidate, float] | None = None
        for candidate in candidates:
            distance = _screen_distance(self._project_candidate(candidate, project), probe_screen)
            if distance > self.acquire_radius_dip:
                continue
            key = (candidate.priority, distance, candidate.stable_id)
            if best is None or key < best[0]:
                best = (key, candidate, distance)
        if best is None:
            self._retained_id = None
            return None
        _, candidate, distance = best
        self._retained_id = candidate.stable_id
        return SnapSelection(candidate, distance)


def _screen_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def _validate_step(step: float, *, label: str) -> float:
    step = float(step)
    if not isfinite(step) or step <= 0.0:
        raise ValueError(f'{label} must be a finite positive value')
    return step


def snap_scalar(value: float, step: float) -> float:
    """Round to the nearest step, with exact halves away from zero."""
    step = _validate_step(step, label='snap step')
    value = float(value)
    if not isfinite(value):
        raise ValueError('snap value must be finite')
    sign = -1.0 if value < 0.0 else 1.0
    return sign * floor(abs(value) / step + 0.5) * step


def snap_position_axis(position: Position3, axis: AxisName, step_m: float) -> Position3:
    step_m = _validate_step(step_m, label='grid step')
    values = {'x': position.x_m, 'y': position.y_m, 'z': position.z_m}
    if axis not in values:
        raise ValueError(f'unsupported snap axis: {axis}')
    values[axis] = snap_scalar(values[axis], step_m)
    return Position3(x_m=values['x'], y_m=values['y'], z_m=values['z'])


def snap_angle_deg(angle_deg: float, step_deg: float) -> float:
    step_deg = _validate_step(step_deg, label='angle step')
    return snap_scalar(float(angle_deg), step_deg)


def _axis_value(position: Position3, axis: AxisName) -> float:
    return {'x': position.x_m, 'y': position.y_m, 'z': position.z_m}[axis]


def _with_axis(position: Position3, axis: AxisName, value: float) -> Position3:
    values = {'x': position.x_m, 'y': position.y_m, 'z': position.z_m}
    values[axis] = float(value)
    return Position3(x_m=values['x'], y_m=values['y'], z_m=values['z'])


def _entity_vertices(entity: SceneEntity) -> tuple[Position3, ...]:
    if entity.size_m is None:
        return (entity.position,)
    matrix = quaternion_to_matrix3(entity.orientation)
    half = (entity.size_m.x_m / 2.0, entity.size_m.y_m / 2.0, entity.size_m.z_m / 2.0)
    result: list[Position3] = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                local = (sx * half[0], sy * half[1], sz * half[2])
                rotated = tuple(
                    sum(matrix[row][col] * local[col] for col in range(3))
                    for row in range(3)
                )
                result.append(Position3(
                    x_m=entity.position.x_m + rotated[0],
                    y_m=entity.position.y_m + rotated[1],
                    z_m=entity.position.z_m + rotated[2],
                ))
    return tuple(result)


def _box_edges(vertices: tuple[Position3, ...]) -> tuple[tuple[int, int], ...]:
    if len(vertices) != 8:
        return ()
    edges: list[tuple[int, int]] = []
    for left in range(8):
        for right in range(left + 1, 8):
            if (left ^ right) in (1, 2, 4):
                edges.append((left, right))
    return tuple(edges)


def _closest_point_on_segment(probe: Position3, start: Position3, end: Position3) -> Position3:
    p = (probe.x_m, probe.y_m, probe.z_m)
    a = (start.x_m, start.y_m, start.z_m)
    b = (end.x_m, end.y_m, end.z_m)
    direction = tuple(b[index] - a[index] for index in range(3))
    length2 = sum(value * value for value in direction)
    if length2 <= 1e-18:
        return start
    t = sum((p[index] - a[index]) * direction[index] for index in range(3)) / length2
    t = max(0.0, min(1.0, t))
    return Position3(
        x_m=a[0] + direction[0] * t,
        y_m=a[1] + direction[1] * t,
        z_m=a[2] + direction[2] * t,
    )


def _candidate(
    entity: SceneEntity,
    kind: SnapKind,
    feature_id: str,
    feature_position: Position3,
    axis: AxisName,
    probe: Position3,
) -> SnapCandidate:
    value = _axis_value(feature_position, axis)
    return SnapCandidate(
        stable_id=f'{entity.entity_id}:{kind}:{feature_id}:{axis}',
        kind=kind,
        entity_id=entity.entity_id,
        target=_with_axis(probe, axis, value),
        screen_anchor=feature_position,
        axis=axis,
        label=f'{kind} · {entity.name} · {axis.upper()}={value:.3f} m',
    )


def generate_snap_candidates(
    document: SceneDocument,
    *,
    exclude_ids: set[str],
    axis: AxisName,
    probe: Position3,
) -> tuple[SnapCandidate, ...]:
    candidates: list[SnapCandidate] = []
    for entity in document.entities:
        if entity.entity_id in exclude_ids:
            continue
        vertices = _entity_vertices(entity)
        for index, vertex in enumerate(vertices):
            candidates.append(_candidate(entity, 'vertex', str(index), vertex, axis, probe))
        if entity.size_m is not None:
            for edge_index, (left, right) in enumerate(_box_edges(vertices)):
                start, end = vertices[left], vertices[right]
                midpoint = Position3(
                    x_m=(start.x_m + end.x_m) / 2.0,
                    y_m=(start.y_m + end.y_m) / 2.0,
                    z_m=(start.z_m + end.z_m) / 2.0,
                )
                closest = _closest_point_on_segment(probe, start, end)
                candidates.append(_candidate(entity, 'midpoint', str(edge_index), midpoint, axis, probe))
                candidates.append(_candidate(entity, 'edge', str(edge_index), closest, axis, probe))
        candidates.append(_candidate(entity, 'alignment', 'origin', entity.position, axis, probe))
    return tuple(candidates)