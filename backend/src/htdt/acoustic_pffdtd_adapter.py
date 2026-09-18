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

    triangles: list[list[int]] = []
    for face in region.faces:
        if len(face.vertex_ids) < 3:
            raise ValueError(f'face {face.face_id} has fewer than three vertices')
        face_points = np.asarray(
            [vertex_by_id[item] for item in face.vertex_ids],
            dtype=np.float64,
        )
        face_centroid = face_points.mean(axis=0)
        for offset in range(1, len(face.vertex_ids) - 1):
            tri_ids = [
                face.vertex_ids[0],
                face.vertex_ids[offset],
                face.vertex_ids[offset + 1],
            ]
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
