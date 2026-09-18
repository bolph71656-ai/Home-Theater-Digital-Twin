from __future__ import annotations

from math import sqrt
from typing import Iterable

from shapely.geometry import LineString, MultiPoint, Point
from shapely.geometry.base import BaseGeometry

from .cad_constraint_models import (
    CadAllowedRegionConstraint,
    CadConstraintSet,
    CadExclusionRegionConstraint,
    CadPairDistanceConstraint,
    CadWallClearanceConstraint,
)
from .cad_scene import SceneDocument, SceneEntity, quaternion_to_matrix3, room_vertices
from .geometry import polygon_from_vertices


_EPS = 1e-9


def entity_horizontal_footprint(entity: SceneEntity) -> BaseGeometry:
    """Return the exact XY projection of the oriented entity body.

    Physical entities use the convex hull of all eight oriented box corners so
    pitch/roll remain conservative in XY. Non-physical entities degrade to a
    point at their world position.
    """

    if entity.size_m is None:
        return Point(float(entity.position.x_m), float(entity.position.y_m))

    hx = float(entity.size_m.x_m) * 0.5
    hy = float(entity.size_m.y_m) * 0.5
    hz = float(entity.size_m.z_m) * 0.5
    matrix = quaternion_to_matrix3(entity.orientation)
    points: list[tuple[float, float]] = []
    for x in (-hx, hx):
        for y in (-hy, hy):
            for z in (-hz, hz):
                local = (x, y, z)
                world_x = float(entity.position.x_m) + sum(
                    matrix[0][column] * local[column] for column in range(3)
                )
                world_y = float(entity.position.y_m) + sum(
                    matrix[1][column] * local[column] for column in range(3)
                )
                points.append((world_x, world_y))
    return MultiPoint(points).convex_hull


def _region(vertices) -> BaseGeometry:
    return polygon_from_vertices(
        [(float(vertex.x_m), float(vertex.y_m)) for vertex in vertices]
    )


def _wall_line(document: SceneDocument, wall_id: str) -> LineString:
    topology = document.wall_topology
    if topology is None:
        raise ValueError('orientation-aware wall clearance requires wall topology')
    wall = next((item for item in topology.walls if item.wall_id == wall_id), None)
    if wall is None:
        raise ValueError(f'orientation-aware wall clearance references unknown wall: {wall_id}')
    vertices = {vertex.vertex_id: vertex for vertex in room_vertices(document.room)}
    try:
        start = vertices[wall.from_vertex_id]
        end = vertices[wall.to_vertex_id]
    except KeyError as exc:
        raise ValueError(
            f'orientation-aware wall clearance references stale wall endpoint: {wall_id}'
        ) from exc
    return LineString(
        (
            (float(start.x_m), float(start.y_m)),
            (float(end.x_m), float(end.y_m)),
        )
    )


def orientation_constraint_rejections(
    document: SceneDocument,
    constraint_set: CadConstraintSet,
    *,
    changed_entity_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return hard-constraint IDs rejected by exact oriented XY envelopes.

    The existing O10 engine remains the base authority for position feasibility.
    This is an additional O80P refinement for body-rotation candidates. Only
    constraints affected by a rotated entity are reevaluated here.
    """

    changed = {str(entity_id) for entity_id in changed_entity_ids}
    if not changed:
        return ()
    if document.room is None:
        raise ValueError('orientation-aware constraints require a room')

    known = {entity.entity_id for entity in document.entities}
    unknown = changed - known
    if unknown:
        raise ValueError(
            'orientation-aware constraints reference unknown entities: '
            + ', '.join(sorted(unknown))
        )

    room_polygon = polygon_from_vertices(
        [(float(vertex.x_m), float(vertex.y_m)) for vertex in room_vertices(document.room)]
    )
    footprints = {
        entity.entity_id: entity_horizontal_footprint(entity)
        for entity in document.entities
    }

    rejected: set[str] = set()
    for entity_id in sorted(changed):
        if not room_polygon.covers(footprints[entity_id]):
            rejected.add(f'__room_boundary__:{entity_id}')

    for constraint in constraint_set.constraints:
        if isinstance(constraint, CadAllowedRegionConstraint):
            region = _region(constraint.vertices)
            for entity_id in constraint.entity_ids:
                if entity_id in changed and not region.covers(footprints[entity_id]):
                    rejected.add(constraint.constraint_id)

        elif isinstance(constraint, CadExclusionRegionConstraint):
            region = _region(constraint.vertices)
            for entity_id in constraint.entity_ids:
                if entity_id in changed and region.intersects(footprints[entity_id]):
                    rejected.add(constraint.constraint_id)

        elif isinstance(constraint, CadWallClearanceConstraint):
            if not changed.intersection(constraint.entity_ids):
                continue
            edge = _wall_line(document, constraint.wall_id)
            for entity_id in constraint.entity_ids:
                if entity_id not in changed:
                    continue
                clearance = float(footprints[entity_id].distance(edge))
                if (
                    (constraint.min_m is not None and clearance + _EPS < constraint.min_m)
                    or (constraint.max_m is not None and clearance > constraint.max_m + _EPS)
                ):
                    rejected.add(constraint.constraint_id)

        elif isinstance(constraint, CadPairDistanceConstraint):
            if not changed.intersection((constraint.entity_a, constraint.entity_b)):
                continue
            if constraint.distance_reference != 'envelope_clearance':
                continue
            distance = float(
                footprints[constraint.entity_a].distance(footprints[constraint.entity_b])
            )
            if (
                (constraint.min_m is not None and distance + _EPS < constraint.min_m)
                or (constraint.max_m is not None and distance > constraint.max_m + _EPS)
            ):
                rejected.add(constraint.constraint_id)

    return tuple(sorted(rejected))
