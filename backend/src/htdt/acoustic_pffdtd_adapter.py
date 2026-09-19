from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import numpy as np


def pffdtd_git_head(upstream_root: Path) -> str:
    return subprocess.check_output(
        ['git', '-C', str(upstream_root), 'rev-parse', 'HEAD'],
        text=True,
    ).strip().lower()


def apply_pffdtd_runtime_compatibility_patches(upstream_root: Path) -> dict[str, object]:
    """Apply the bounded shims required by the pinned upstream on Python 3.12.

    Every edit is exact-source-checked. The returned diff hash is part of R100B
    evidence so a future upstream change cannot be patched silently.
    """

    patches = (
        {
            'patch_id': 'numpy-removed-np-float-alias-v1',
            'path': 'python/common/myfuncs.py',
            'before': 'EPS = np.finfo(np.float).eps',
            'after': 'EPS = np.finfo(float).eps',
        },
        {
            'patch_id': 'python312-shared-memory-exported-view-cleanup-v1',
            'path': 'python/voxelizer/vox_grid_base.py',
            'before': (
                '            #cleanup shared memory\n'
                '            Ntris_vox_shm.close()\n'
                '            Ntris_vox_shm.unlink()\n\n'
                '            N_tribox_tests_shm.close()\n'
                '            N_tribox_tests_shm.unlink()'
            ),
            'after': (
                '            #cleanup shared memory\n'
                '            del Ntris_vox\n'
                '            del N_tribox_tests\n'
                '            Ntris_vox_shm.close()\n'
                '            Ntris_vox_shm.unlink()\n\n'
                '            N_tribox_tests_shm.close()\n'
                '            N_tribox_tests_shm.unlink()'
            ),
        },
        {
            'patch_id': 'python312-vox-scene-shared-memory-view-cleanup-v1',
            'path': 'python/voxelizer/vox_scene.py',
            'before': (
                '        #clean up shared memory\n'
                '        Nb_proc_shm.close()\n'
                '        Nb_proc_shm.unlink()'
            ),
            'after': (
                '        #clean up shared memory\n'
                '        del Nb_proc\n'
                '        Nb_proc_shm.close()\n'
                '        Nb_proc_shm.unlink()'
            ),
        },
    )

    applied: list[dict[str, str]] = []
    for patch in patches:
        relative_path = Path(patch['path'])
        source_path = upstream_root / relative_path
        source = source_path.read_text(encoding='utf-8')
        before = patch['before']
        after = patch['after']
        if source.count(before) != 1:
            raise RuntimeError(
                f"PFFDTD compatibility patch {patch['patch_id']} expected exactly one "
                f"{before!r} in {relative_path.as_posix()}"
            )
        source_path.write_text(source.replace(before, after, 1), encoding='utf-8')
        applied.append(
            {
                'patch_id': patch['patch_id'],
                'path': relative_path.as_posix(),
                'before_sha256': hashlib.sha256(before.encode('utf-8')).hexdigest(),
                'after_sha256': hashlib.sha256(after.encode('utf-8')).hexdigest(),
            }
        )

    diff = subprocess.check_output(
        ['git', '-C', str(upstream_root), 'diff', '--'],
        text=True,
    )
    changed = sorted(
        subprocess.check_output(
            ['git', '-C', str(upstream_root), 'diff', '--name-only'],
            text=True,
        ).splitlines()
    )
    expected_changed = sorted(patch['path'] for patch in patches)
    if changed != expected_changed:
        raise RuntimeError(
            f'unexpected PFFDTD compatibility patch file set: {changed}; '
            f'expected {expected_changed}'
        )

    return {
        'patches': applied,
        'changed_files': changed,
        'diff_sha256': hashlib.sha256(diff.encode('utf-8')).hexdigest(),
    }


def acoustic_position_array(position) -> np.ndarray:
    return np.asarray([position.x_m, position.y_m, position.z_m], dtype=np.float64)


def _polygon_projection(points: np.ndarray) -> tuple[np.ndarray, int]:
    if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 3:
        raise ValueError('polygon projection requires at least three 3D points')

    normal = np.zeros(3, dtype=np.float64)
    for current, following in zip(points, np.roll(points, -1, axis=0), strict=True):
        normal[0] += (current[1] - following[1]) * (current[2] + following[2])
        normal[1] += (current[2] - following[2]) * (current[0] + following[0])
        normal[2] += (current[0] - following[0]) * (current[1] + following[1])

    drop_axis = int(np.argmax(np.abs(normal)))
    if abs(float(normal[drop_axis])) <= 1.0e-12:
        raise ValueError('polygon face is degenerate or has no stable projection plane')
    projected = np.delete(points, drop_axis, axis=1)
    return projected, drop_axis


def _signed_area_2d(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _cross_2d(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    return float(
        (b[0] - a[0]) * (c[1] - a[1])
        - (b[1] - a[1]) * (c[0] - a[0])
    )


def _is_concave_polygon(points: np.ndarray) -> bool:
    projected, _ = _polygon_projection(points)
    signed_area = _signed_area_2d(projected)
    if abs(signed_area) <= 1.0e-12:
        raise ValueError('polygon face has zero projected area')
    orientation = 1.0 if signed_area > 0.0 else -1.0
    for index in range(projected.shape[0]):
        turn = _cross_2d(
            projected[index - 1],
            projected[index],
            projected[(index + 1) % projected.shape[0]],
        )
        if orientation * turn < -1.0e-12:
            return True
    return False


def _point_in_triangle_2d(
    point: np.ndarray,
    a: np.ndarray,
    b: np.ndarray,
    c: np.ndarray,
    *,
    orientation: float,
) -> bool:
    return (
        orientation * _cross_2d(a, b, point) >= -1.0e-12
        and orientation * _cross_2d(b, c, point) >= -1.0e-12
        and orientation * _cross_2d(c, a, point) >= -1.0e-12
    )


def _triangulate_polygon_indices(points: np.ndarray) -> list[list[int]]:
    projected, _ = _polygon_projection(points)
    signed_area = _signed_area_2d(projected)
    if abs(signed_area) <= 1.0e-12:
        raise ValueError('polygon face has zero projected area')
    orientation = 1.0 if signed_area > 0.0 else -1.0

    if not _is_concave_polygon(points):
        return [[0, offset, offset + 1] for offset in range(1, len(points) - 1)]

    remaining = list(range(len(points)))
    triangles: list[list[int]] = []
    while len(remaining) > 3:
        ear_found = False
        for position, current in enumerate(remaining):
            previous = remaining[position - 1]
            following = remaining[(position + 1) % len(remaining)]
            a = projected[previous]
            b = projected[current]
            c = projected[following]
            if orientation * _cross_2d(a, b, c) <= 1.0e-12:
                continue

            contains_other = False
            for candidate in remaining:
                if candidate in {previous, current, following}:
                    continue
                if _point_in_triangle_2d(
                    projected[candidate],
                    a,
                    b,
                    c,
                    orientation=orientation,
                ):
                    contains_other = True
                    break
            if contains_other:
                continue

            triangles.append([previous, current, following])
            del remaining[position]
            ear_found = True
            break

        if not ear_found:
            raise ValueError('deterministic ear clipping could not triangulate polygon face')

    triangles.append(list(remaining))

    polygon_area = abs(signed_area)
    triangle_area = sum(
        abs(
            _cross_2d(
                projected[triangle[0]],
                projected[triangle[1]],
                projected[triangle[2]],
            )
        )
        * 0.5
        for triangle in triangles
    )
    if not np.isclose(triangle_area, polygon_area, rtol=0.0, atol=1.0e-10):
        raise ValueError(
            f'polygon triangulation area mismatch: triangles={triangle_area}, polygon={polygon_area}'
        )
    return triangles


def _edge_direction(triangle: list[int], a: int, b: int) -> int:
    for offset in range(3):
        current = triangle[offset]
        following = triangle[(offset + 1) % 3]
        if current == a and following == b:
            return 1
        if current == b and following == a:
            return -1
    raise ValueError(f'triangle {triangle} does not contain shared edge {(a, b)}')


def _orient_closed_triangle_mesh_outward(
    triangles: list[list[int]],
    points: np.ndarray,
) -> list[list[int]]:
    oriented = [list(triangle) for triangle in triangles]
    edge_to_triangles: dict[tuple[int, int], list[int]] = {}
    for triangle_index, triangle in enumerate(oriented):
        for offset in range(3):
            a = triangle[offset]
            b = triangle[(offset + 1) % 3]
            edge = (min(a, b), max(a, b))
            edge_to_triangles.setdefault(edge, []).append(triangle_index)

    nonmanifold = {
        edge: owners
        for edge, owners in edge_to_triangles.items()
        if len(owners) != 2
    }
    if nonmanifold:
        raise ValueError(
            f'compiled rigid surface is not a closed two-manifold: {nonmanifold}'
        )

    adjacency: dict[int, list[tuple[int, tuple[int, int]]]] = {
        index: [] for index in range(len(oriented))
    }
    for edge, owners in edge_to_triangles.items():
        first, second = owners
        adjacency[first].append((second, edge))
        adjacency[second].append((first, edge))

    visited = {0}
    queue = [0]
    while queue:
        current = queue.pop(0)
        for neighbor, edge in adjacency[current]:
            current_direction = _edge_direction(oriented[current], *edge)
            neighbor_direction = _edge_direction(oriented[neighbor], *edge)
            needs_flip = current_direction == neighbor_direction
            if neighbor in visited:
                if needs_flip:
                    raise ValueError('compiled rigid surface has inconsistent triangle orientation')
                continue
            if needs_flip:
                oriented[neighbor] = [
                    oriented[neighbor][0],
                    oriented[neighbor][2],
                    oriented[neighbor][1],
                ]
            visited.add(neighbor)
            queue.append(neighbor)

    if len(visited) != len(oriented):
        raise ValueError('compiled rigid surface contains disconnected triangle components')

    signed_volume = sum(
        float(
            np.dot(
                points[triangle[0]],
                np.cross(points[triangle[1]], points[triangle[2]]),
            )
        )
        / 6.0
        for triangle in oriented
    )
    if abs(signed_volume) <= 1.0e-12:
        raise ValueError('compiled rigid surface has zero signed volume')
    if signed_volume < 0.0:
        oriented = [
            [triangle[0], triangle[2], triangle[1]]
            for triangle in oriented
        ]
    return oriented


def compile_rigid_fixture_model(fixture) -> dict[str, object]:
    """Compile one closed rigid R100A region into PFFDTD's JSON mesh authority."""

    if fixture.portals or fixture.terminations or fixture.obstacles:
        raise ValueError('PFFDTD rigid fixture compiler expects one closed obstacle-free region')
    if len(fixture.regions) != 1 or len(fixture.sources) != 1 or len(fixture.receivers) != 1:
        raise ValueError('PFFDTD rigid fixture compiler expects one region/source/receiver')

    boundary_by_id = {item.boundary_id: item for item in fixture.boundaries}
    material_by_id = {item.material_id: item for item in fixture.materials}
    for face in fixture.regions[0].faces:
        boundary = boundary_by_id.get(face.boundary_id)
        if boundary is None:
            raise ValueError(f'unknown boundary on face {face.face_id}: {face.boundary_id}')
        material = material_by_id.get(boundary.material_id)
        if material is None or material.wave_model != 'rigid':
            raise ValueError(
                f'PFFDTD rigid fixture compiler refuses non-rigid face {face.face_id}'
            )

    region = fixture.regions[0]
    vertex_by_id = {
        vertex.vertex_id: acoustic_position_array(vertex.position)
        for vertex in region.vertices
    }
    vertex_ids = list(vertex_by_id)
    index_by_id = {vertex_id: index for index, vertex_id in enumerate(vertex_ids)}
    points = np.asarray([vertex_by_id[vertex_id] for vertex_id in vertex_ids], dtype=np.float64)
    region_centroid = points.mean(axis=0)
    has_concave_face = any(
        _is_concave_polygon(
            np.asarray([vertex_by_id[item] for item in face.vertex_ids], dtype=np.float64)
        )
        for face in region.faces
    )

    triangles: list[list[int]] = []
    for face in region.faces:
        if len(face.vertex_ids) < 3:
            raise ValueError(f'face {face.face_id} has fewer than three vertices')
        face_points = np.asarray(
            [vertex_by_id[item] for item in face.vertex_ids],
            dtype=np.float64,
        )
        local_triangles = _triangulate_polygon_indices(face_points)
        for local_triangle in local_triangles:
            tri_ids = [face.vertex_ids[index] for index in local_triangle]
            if not has_concave_face:
                # Preserve the existing convex-fixture output path exactly.
                face_centroid = face_points.mean(axis=0)
                tri_points = np.asarray(
                    [vertex_by_id[item] for item in tri_ids],
                    dtype=np.float64,
                )
                normal = np.cross(
                    tri_points[1] - tri_points[0],
                    tri_points[2] - tri_points[0],
                )
                if float(np.dot(normal, face_centroid - region_centroid)) < 0.0:
                    tri_ids = [tri_ids[0], tri_ids[2], tri_ids[1]]
            triangles.append([index_by_id[item] for item in tri_ids])

    if has_concave_face:
        # A vertex average can lie outside a concave region (the L-room average
        # falls inside its notch), so centroid-based face flipping is invalid.
        # Propagate a consistent orientation over the closed two-manifold, then
        # use signed volume to choose the globally outward orientation.
        triangles = _orient_closed_triangle_mesh_outward(triangles, points)

    return {
        'mats_hash': {
            '_RIGID': {
                'tris': triangles,
                'pts': points.tolist(),
                'color': [220, 220, 220],
                'sides': [0] * len(triangles),
            }
        },
        'sources': [
            {
                'xyz': acoustic_position_array(fixture.sources[0].position).tolist(),
                'name': fixture.sources[0].source_id,
            }
        ],
        'receivers': [
            {
                'xyz': acoustic_position_array(fixture.receivers[0].position).tolist(),
                'name': fixture.receivers[0].receiver_id,
            }
        ],
        'export_datetime': 'R100B deterministic fixture compiler',
    }


def recombine_pffdtd_receiver_traces(
    raw_grid_output: np.ndarray,
    out_alpha: np.ndarray,
    *,
    receiver_count: int,
    nt: int,
) -> np.ndarray:
    """Recombine PFFDTD raw grid traces exactly as ProcessOutputs.initial_process."""

    output = np.asarray(raw_grid_output, dtype=np.float64)
    weights = np.asarray(out_alpha, dtype=np.float64)
    if output.ndim != 2 or output.shape != (weights.size, nt):
        raise ValueError(
            f'raw PFFDTD output/weight mismatch: output={output.shape}, '
            f'weights={weights.shape}, nt={nt}'
        )
    if weights.ndim != 2 or weights.shape[0] != receiver_count:
        raise ValueError(
            f'PFFDTD interpolation weight receiver mismatch: {weights.shape}; '
            f'expected receiver_count={receiver_count}'
        )
    if not np.all(np.isfinite(output)) or not np.all(np.isfinite(weights)):
        raise ValueError('PFFDTD raw output/interpolation weights must be finite')

    recombined = np.sum(
        (output * weights.flat[:][:, None]).reshape((*weights.shape, -1)),
        axis=1,
    )
    if recombined.shape != (receiver_count, nt):
        raise ValueError(
            f'unexpected recombined PFFDTD receiver shape: {recombined.shape}; '
            f'expected {(receiver_count, nt)}'
        )
    if not np.all(np.isfinite(recombined)):
        raise ValueError('PFFDTD recombined receiver output contains non-finite values')
    return recombined


def pffdtd_velocity_potential_to_pressure_transfer(
    velocity_potential_trace: np.ndarray,
    source_volume_velocity_trace: np.ndarray,
    *,
    time_step_s: float,
    frequency_hz: np.ndarray,
    density_kg_m3: float,
) -> np.ndarray:
    """Convert PFFDTD velocity potential to pressure/volume-velocity transfer.

    PFFDTD state u is acoustic velocity potential. With HTDT's
    exp(-i*omega*t) convention, p = -rho * d(phi)/dt becomes
    P = -i*omega*rho*Phi. The same finite-record DTFT is applied to the
    physical pre-grid source volume-velocity samples, so the common time-step
    factor cancels in P/Q.
    """

    phi = np.asarray(velocity_potential_trace, dtype=np.float64)
    source = np.asarray(source_volume_velocity_trace, dtype=np.float64)
    frequencies = np.asarray(frequency_hz, dtype=np.float64)

    if phi.ndim != 1 or source.ndim != 1 or phi.shape != source.shape:
        raise ValueError(
            f'PFFDTD pressure conversion requires matching 1D traces: '
            f'phi={phi.shape}, source={source.shape}'
        )
    if phi.size < 2:
        raise ValueError('PFFDTD pressure conversion requires at least two time samples')
    if not np.all(np.isfinite(phi)) or not np.all(np.isfinite(source)):
        raise ValueError('PFFDTD pressure conversion traces must be finite')
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError('PFFDTD pressure conversion requires a non-empty 1D frequency grid')
    if not np.all(np.isfinite(frequencies)) or np.any(frequencies <= 0.0):
        raise ValueError('PFFDTD pressure conversion frequencies must be finite and positive')
    if not np.isfinite(time_step_s) or time_step_s <= 0.0:
        raise ValueError('PFFDTD pressure conversion time_step_s must be finite and positive')
    if not np.isfinite(density_kg_m3) or density_kg_m3 <= 0.0:
        raise ValueError('PFFDTD pressure conversion density_kg_m3 must be finite and positive')

    times = np.arange(phi.size, dtype=np.float64) * float(time_step_s)
    kernel = np.exp(-2j * np.pi * frequencies[:, None] * times[None, :])
    phi_spectrum = kernel @ phi
    source_spectrum = kernel @ source

    source_floor = np.finfo(np.float64).eps * max(
        1.0, float(np.max(np.abs(source_spectrum)))
    )
    if np.any(np.abs(source_spectrum) <= source_floor):
        raise ValueError('PFFDTD physical source spectrum is zero on the comparison grid')

    omega = 2.0 * np.pi * frequencies
    transfer = (-1j * omega * float(density_kg_m3)) * phi_spectrum / source_spectrum
    if not np.all(np.isfinite(transfer.real)) or not np.all(np.isfinite(transfer.imag)):
        raise ValueError('PFFDTD pressure transfer contains non-finite values')
    return transfer
