from __future__ import annotations

import hashlib
from math import isfinite
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


def compile_impedance_fixture_boundary(fixture) -> dict[str, object]:
    """Map explicit R100A impedance authority to PFFDTD's direct DEF subset.

    PFFDTD's material state is a normalized specific-admittance DEF network.
    A frequency-independent, purely resistive specific impedance maps exactly to
    one branch DEF=[0, Z/(rho*c), 0]. This adapter deliberately refuses
    reactive or frequency-varying tables because representing them would require
    a fitting policy that is not part of R100A authority.
    """

    if fixture.comparison.frequency_grid.kind != 'explicit':
        raise ValueError('PFFDTD impedance adapter requires an explicit R100A frequency grid')
    frequencies_hz = tuple(
        float(value) for value in fixture.comparison.frequency_grid.values_hz
    )
    if not frequencies_hz:
        raise ValueError('PFFDTD impedance adapter requires non-empty fixture frequencies')

    boundary_by_id = {item.boundary_id: item for item in fixture.boundaries}
    material_by_id = {item.material_id: item for item in fixture.materials}
    impedance_material_ids: set[str] = set()
    has_rigid = False
    for face in fixture.regions[0].faces:
        boundary = boundary_by_id.get(face.boundary_id)
        if boundary is None:
            raise ValueError(f'unknown boundary on face {face.face_id}: {face.boundary_id}')
        material = material_by_id.get(boundary.material_id)
        if material is None:
            raise ValueError(f'unknown material on boundary {boundary.boundary_id}')
        if material.wave_model == 'rigid':
            has_rigid = True
        elif material.wave_model == 'specific_impedance_table':
            impedance_material_ids.add(material.material_id)
        else:
            raise ValueError(
                f'PFFDTD impedance adapter refuses unsupported wave material {material.material_id}'
            )

    if not has_rigid:
        raise ValueError('PFFDTD impedance fixture requires explicit rigid companion boundaries')
    if len(impedance_material_ids) != 1:
        raise ValueError(
            'PFFDTD impedance fixture requires exactly one explicit impedance material'
        )

    material_id = next(iter(impedance_material_ids))
    material = material_by_id[material_id]
    table = material.specific_impedance
    table_frequencies = tuple(float(item.frequency_hz) for item in table)
    if table_frequencies != frequencies_hz:
        raise ValueError(
            'PFFDTD direct impedance adapter requires impedance samples on the exact '
            'R100A comparison frequency grid'
        )

    reactances = tuple(float(item.reactance_pa_s_m) for item in table)
    if any(value != 0.0 for value in reactances):
        raise ValueError(
            'PFFDTD direct impedance adapter refuses reactive impedance authority; '
            'no table-to-DEF fitting policy is authorized'
        )

    resistances = tuple(float(item.resistance_pa_s_m) for item in table)
    if not resistances or any(not isfinite(value) or value <= 0.0 for value in resistances):
        raise ValueError('PFFDTD direct impedance adapter requires finite positive resistance')
    resistance = resistances[0]
    if any(value != resistance for value in resistances[1:]):
        raise ValueError(
            'PFFDTD direct impedance adapter refuses frequency-varying resistance; '
            'no table-to-DEF fitting policy is authorized'
        )

    density = float(fixture.environment.density_kg_m3)
    sound_speed = float(fixture.environment.sound_speed_m_s)
    characteristic_impedance = density * sound_speed
    if not isfinite(characteristic_impedance) or characteristic_impedance <= 0.0:
        raise ValueError('R100A density/sound-speed authority produces invalid rho*c')

    normalized_impedance = resistance / characteristic_impedance
    if not isfinite(normalized_impedance) or normalized_impedance <= 0.0:
        raise ValueError('normalized PFFDTD impedance must be finite and positive')
    normalized_admittance = 1.0 / normalized_impedance
    coefficients = np.asarray([[0.0, normalized_impedance, 0.0]], dtype=np.float64)

    return {
        'material_id': material_id,
        'material_version': material.version,
        'material_provenance': material.provenance,
        'frequencies_hz': frequencies_hz,
        'physical_resistance_pa_s_m': resistance,
        'physical_reactance_pa_s_m': 0.0,
        'density_kg_m3': density,
        'sound_speed_m_s': sound_speed,
        'characteristic_impedance_pa_s_m': characteristic_impedance,
        'normalized_impedance': normalized_impedance,
        'normalized_admittance': normalized_admittance,
        'def_coefficients': coefficients,
        'mapping': 'exact_frequency_independent_resistive_Z_to_DEF',
    }


def compile_impedance_fixture_model(fixture) -> dict[str, object]:
    """Compile the canonical closed impedance fixture into PFFDTD material groups."""

    if fixture.portals or fixture.terminations or fixture.obstacles:
        raise ValueError('PFFDTD impedance fixture compiler expects one closed obstacle-free region')
    if len(fixture.regions) != 1 or len(fixture.sources) != 1 or len(fixture.receivers) != 1:
        raise ValueError('PFFDTD impedance fixture compiler expects one region/source/receiver')

    boundary_info = compile_impedance_fixture_boundary(fixture)
    impedance_material_id = str(boundary_info['material_id'])
    boundary_by_id = {item.boundary_id: item for item in fixture.boundaries}
    material_by_id = {item.material_id: item for item in fixture.materials}
    region = fixture.regions[0]
    vertex_by_id = {
        vertex.vertex_id: acoustic_position_array(vertex.position)
        for vertex in region.vertices
    }
    all_points = np.asarray(list(vertex_by_id.values()), dtype=np.float64)
    region_centroid = all_points.mean(axis=0)

    faces_by_group: dict[str, list[object]] = {}
    for face in region.faces:
        boundary = boundary_by_id.get(face.boundary_id)
        if boundary is None:
            raise ValueError(f'unknown boundary on face {face.face_id}: {face.boundary_id}')
        material = material_by_id.get(boundary.material_id)
        if material is None:
            raise ValueError(f'unknown material on boundary {boundary.boundary_id}')
        if material.wave_model == 'rigid':
            group = '_RIGID'
        elif material.material_id == impedance_material_id:
            group = impedance_material_id
        else:
            raise ValueError(f'unexpected impedance fixture material {material.material_id}')
        faces_by_group.setdefault(group, []).append(face)

    if set(faces_by_group) != {'_RIGID', impedance_material_id}:
        raise ValueError('PFFDTD impedance fixture compiler requires rigid and impedance groups')

    mats_hash: dict[str, object] = {}
    for group, faces in faces_by_group.items():
        local_vertex_ids: list[str] = []
        for face in faces:
            for vertex_id in face.vertex_ids:
                if vertex_id not in local_vertex_ids:
                    local_vertex_ids.append(vertex_id)
        local_index = {vertex_id: index for index, vertex_id in enumerate(local_vertex_ids)}
        local_points = np.asarray(
            [vertex_by_id[vertex_id] for vertex_id in local_vertex_ids],
            dtype=np.float64,
        )

        triangles: list[list[int]] = []
        for face in faces:
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
                triangles.append([local_index[item] for item in tri_ids])

        mats_hash[group] = {
            'tris': triangles,
            'pts': local_points.tolist(),
            'color': [220, 220, 220] if group == '_RIGID' else [180, 190, 220],
            'sides': [0] * len(triangles),
        }

    return {
        'mats_hash': mats_hash,
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
        'export_datetime': 'R100B deterministic impedance fixture compiler',
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
