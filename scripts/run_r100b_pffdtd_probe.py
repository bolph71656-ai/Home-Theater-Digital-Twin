from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
import traceback

import h5py
import numpy as np
import psutil

from htdt.acoustic_bakeoff import (
    BakeoffFixtureEvidence,
    BakeoffHardGateEvidence,
    BakeoffPlatform,
    BakeoffRun,
    load_bakeoff_candidate_manifest,
    validate_bakeoff_run,
)
from htdt.acoustic_benchmark import load_acoustic_benchmark_manifest


CANDIDATE_ID = 'pffdtd-main-aa319f6'
FIXTURE_ID = 'wave-rigid-rectangular-modes-v1'
PROBE_SCHEMA = 'r100b-platform-probe-artifact-1'
PROBE_ID = 'pffdtd-python-numba-windows-execution-smoke'
ADAPTER_ID = 'htdt-r100b-pffdtd-python-smoke'
ADAPTER_VERSION = '4'
FMAX_HZ = 100.0
PPW = 7.5
DURATION_S = 0.03
THREAD_BUDGET = 4
NPROCS = 1


class PeakRssMonitor:
    def __init__(self) -> None:
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self.peak_bytes = self._process.memory_info().rss

    def _sample(self) -> None:
        while not self._stop.wait(0.005):
            self.peak_bytes = max(self.peak_bytes, self._process.memory_info().rss)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> float:
        self.peak_bytes = max(self.peak_bytes, self._process.memory_info().rss)
        self._stop.set()
        self._thread.join(timeout=1.0)
        return self.peak_bytes / (1024.0 * 1024.0)


def _candidate(candidates):
    return next(item for item in candidates.candidates if item.candidate_id == CANDIDATE_ID)


def _fixture(benchmark):
    return next(item for item in benchmark.fixtures if item.fixture_id == FIXTURE_ID)


def _position(position) -> np.ndarray:
    return np.asarray([position.x_m, position.y_m, position.z_m], dtype=np.float64)


def _runtime_versions() -> dict[str, str]:
    names = ('numpy', 'numba', 'h5py', 'scipy', 'tqdm', 'psutil', 'memory-profiler')
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = 'not-installed'
    return versions


def _git_head(upstream_root: Path) -> str:
    return subprocess.check_output(
        ['git', '-C', str(upstream_root), 'rev-parse', 'HEAD'],
        text=True,
    ).strip().lower()


def _apply_compatibility_patches(upstream_root: Path) -> dict[str, object]:
    """Apply bounded, exact-source-checked runtime compatibility shims.

    The pinned PFFDTD commit predates two Python/NumPy runtime changes that
    otherwise prevent the existing Python/Numba CPU path from executing on the
    current Windows/Python 3.12 CI image. Refuse to patch if any expected source
    text differs, and record the complete diff hash.
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


def _platform() -> BakeoffPlatform:
    logical_threads = os.cpu_count() or 1
    return BakeoffPlatform(
        os=platform.platform(),
        architecture=platform.machine() or 'unknown',
        python_version=platform.python_version(),
        cpu=platform.processor() or os.environ.get('PROCESSOR_IDENTIFIER', 'unknown'),
        logical_threads=logical_threads,
        thread_budget=min(THREAD_BUDGET, logical_threads),
        gpu=None,
        device_notes='GitHub-hosted Windows PFFDTD Python/Numba CPU execution smoke; no GPU.',
    )


def _hard_gates(evidence_ref: str, reproducible: bool) -> tuple[BakeoffHardGateEvidence, ...]:
    categories = (
        'physics_correctness',
        'cpu_baseline',
        'windows_packaging',
        'license_redistribution',
        'required_capability',
        'reproducible_authority',
    )
    result: list[BakeoffHardGateEvidence] = []
    for category in categories:
        if category == 'reproducible_authority' and reproducible:
            result.append(
                BakeoffHardGateEvidence(
                    category=category,
                    status='pass',
                    evidence_ref=evidence_ref,
                    summary=(
                        'Pinned PFFDTD source commit, exact HTDT/R100A authority hashes, '
                        'runtime dependency versions, probe controls, platform and execution '
                        'measurements are recorded in the artifact.'
                    ),
                )
            )
        else:
            result.append(
                BakeoffHardGateEvidence(
                    category=category,
                    status='not_run',
                    summary=(
                        'This platform smoke does not score candidate-wide R100B hard gates. '
                        'Physics correctness and CPU baseline require dedicated R100A numerical '
                        'evidence; source-checkout execution is not Windows product packaging.'
                    ),
                )
            )
    return tuple(result)


def _make_run(benchmark, candidates, evidence_ref: str, outcome: str, diagnostic: str) -> BakeoffRun:
    candidate = _candidate(candidates)
    fixture = _fixture(benchmark)
    run = BakeoffRun(
        run_id=f'pffdtd-python-smoke-{os.environ.get("GITHUB_RUN_ID", "manual")}',
        r100a_manifest_id=benchmark.manifest_id,
        r100a_semantic_hash=benchmark.semantic_hash(),
        candidate_manifest_hash=candidates.semantic_hash(),
        candidate_id=candidate.candidate_id,
        candidate_source_commit_sha=candidate.source_commit_sha,
        platform=_platform(),
        fixture_evidence=(
            BakeoffFixtureEvidence(
                fixture_id=fixture.fixture_id,
                status='not_run',
                adapter_id=ADAPTER_ID,
                adapter_version=ADAPTER_VERSION,
                backend_version=candidate.source_commit_sha[:12],
                precision='float64',
                diagnostics=(
                    'PFFDTD engine execution smoke only; R100A eigenfrequency observables were not evaluated.',
                    f'platform_probe_outcome={outcome}',
                    diagnostic,
                ),
            ),
        ),
        hard_gates=_hard_gates(evidence_ref, reproducible=outcome == 'pass'),
        notes=(
            'PFFDTD Python/Numba CPU path is probed before any C/CUDA port or custom kernel.',
            'Smoke controls are not R100A numerical acceptance parameters.',
        ),
    )
    validate_bakeoff_run(benchmark, candidates, run)
    return run


def _triangulated_rigid_model(fixture) -> dict[str, object]:
    if fixture.portals or fixture.terminations or fixture.obstacles:
        raise ValueError('rigid PFFDTD smoke expects one closed obstacle-free region')
    if len(fixture.regions) != 1 or len(fixture.sources) != 1 or len(fixture.receivers) != 1:
        raise ValueError('rigid PFFDTD smoke expects one region/source/receiver')

    region = fixture.regions[0]
    vertex_by_id = {vertex.vertex_id: _position(vertex.position) for vertex in region.vertices}
    vertex_ids = list(vertex_by_id)
    index_by_id = {vertex_id: index for index, vertex_id in enumerate(vertex_ids)}
    points = np.asarray([vertex_by_id[vertex_id] for vertex_id in vertex_ids], dtype=np.float64)
    region_centroid = points.mean(axis=0)

    triangles: list[list[int]] = []
    for face in region.faces:
        if len(face.vertex_ids) < 3:
            raise ValueError(f'face {face.face_id} has fewer than three vertices')
        face_points = np.asarray([vertex_by_id[item] for item in face.vertex_ids], dtype=np.float64)
        face_centroid = face_points.mean(axis=0)
        for offset in range(1, len(face.vertex_ids) - 1):
            tri_ids = [face.vertex_ids[0], face.vertex_ids[offset], face.vertex_ids[offset + 1]]
            tri_points = np.asarray([vertex_by_id[item] for item in tri_ids], dtype=np.float64)
            normal = np.cross(tri_points[1] - tri_points[0], tri_points[2] - tri_points[0])
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
            {'xyz': _position(fixture.sources[0].position).tolist(), 'name': fixture.sources[0].source_id}
        ],
        'receivers': [
            {'xyz': _position(fixture.receivers[0].position).tolist(), 'name': fixture.receivers[0].receiver_id}
        ],
        'export_datetime': 'R100B deterministic fixture compiler',
    }


def _directory_size_mb(path: Path) -> float:
    return sum(item.stat().st_size for item in path.rglob('*') if item.is_file()) / (1024.0 * 1024.0)


def _execute(upstream_root: Path, work_dir: Path, benchmark, candidates) -> dict[str, object]:
    candidate = _candidate(candidates)
    fixture = _fixture(benchmark)
    actual_head = _git_head(upstream_root)
    if actual_head != candidate.source_commit_sha:
        raise RuntimeError(
            f'PFFDTD checkout mismatch: expected {candidate.source_commit_sha}, got {actual_head}'
        )

    compatibility_patch = _apply_compatibility_patches(upstream_root)

    upstream_python = upstream_root / 'python'
    if not (upstream_python / 'sim_setup.py').is_file():
        raise RuntimeError(f'PFFDTD Python runtime missing: {upstream_python}')
    sys.path.insert(0, str(upstream_python))

    from sim_setup import sim_setup
    from fdtd.sim_fdtd import SimEngine

    work_dir.mkdir(parents=True, exist_ok=True)
    sim_dir = work_dir / 'sim'
    sim_dir.mkdir(parents=True, exist_ok=True)
    material_dir = work_dir / 'materials'
    material_dir.mkdir(parents=True, exist_ok=True)
    model_path = work_dir / 'r100a_rigid_box_pffdtd.json'
    model = _triangulated_rigid_model(fixture)
    model_path.write_text(json.dumps(model, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    monitor = PeakRssMonitor()
    monitor.start()
    setup_started = time.perf_counter()
    sim_setup(
        insig_type='impulse',
        fmax=FMAX_HZ,
        PPW=PPW,
        save_folder=sim_dir,
        model_json_file=model_path,
        mat_folder=material_dir,
        mat_files_dict={},
        duration=DURATION_S,
        Tc=float(fixture.environment.temperature_c),
        rh=float(fixture.environment.relative_humidity_percent or 50.0),
        source_num=1,
        draw_vox=False,
        fcc_flag=False,
        Nprocs=NPROCS,
        compress=0,
    )
    setup_s = time.perf_counter() - setup_started

    prepare_started = time.perf_counter()
    engine = SimEngine(sim_dir, energy_on=False, nthreads=min(THREAD_BUDGET, os.cpu_count() or 1))
    engine.load_h5_data()
    engine.setup_mask()
    engine.allocate_mem()
    engine.set_coeffs()
    engine.checks()
    prepare_s = time.perf_counter() - prepare_started

    solve_started = time.perf_counter()
    engine.run_all(nsteps=max(1, min(16, int(engine.Nt))))
    solve_s = time.perf_counter() - solve_started

    save_started = time.perf_counter()
    engine.save_outputs()
    save_s = time.perf_counter() - save_started
    peak_ram_mb = monitor.stop()

    output_path = sim_dir / 'sim_outs.h5'
    if not output_path.is_file():
        raise RuntimeError('PFFDTD did not produce sim_outs.h5')
    with h5py.File(output_path, 'r') as handle:
        output = np.asarray(handle['u_out'][...], dtype=np.float64)
    if output.ndim != 2 or output.shape[0] != len(fixture.receivers):
        raise RuntimeError(f'unexpected PFFDTD output shape: {output.shape}')
    if not np.all(np.isfinite(output)):
        raise RuntimeError('PFFDTD output contains non-finite values')
    max_abs = float(np.max(np.abs(output))) if output.size else 0.0
    nonzero_samples = int(np.count_nonzero(output))
    if max_abs <= 0.0 or nonzero_samples == 0:
        raise RuntimeError('PFFDTD output contains no propagated signal')

    expected_dims = np.ptp(
        np.asarray([_position(vertex.position) for vertex in fixture.regions[0].vertices]),
        axis=0,
    )

    return {
        'probe_scope': 'windows_python_numba_execution_smoke',
        'physics_evaluated': False,
        'candidate_id': candidate.candidate_id,
        'candidate_source_commit_sha': candidate.source_commit_sha,
        'upstream_git_head': actual_head,
        'fixture_id': fixture.fixture_id,
        'authority_room_extent_m': expected_dims.tolist(),
        'authority_source_m': _position(fixture.sources[0].position).tolist(),
        'authority_receiver_m': _position(fixture.receivers[0].position).tolist(),
        'probe_controls': {
            'fmax_hz': FMAX_HZ,
            'points_per_wavelength': PPW,
            'duration_s': DURATION_S,
            'fcc_flag': False,
            'setup_processes': NPROCS,
            'solver_thread_budget': min(THREAD_BUDGET, os.cpu_count() or 1),
            'input_signal': 'impulse',
            'material_mapping': '_RIGID / no impedance file',
            'triangle_orientation': 'outward',
        },
        'runtime_versions': _runtime_versions(),
        'compatibility_patch': compatibility_patch,
        'pffdtd_runtime': {
            'Nx': int(engine.Nx),
            'Ny': int(engine.Ny),
            'Nz': int(engine.Nz),
            'Nt': int(engine.Nt),
            'Nr': int(engine.Nr),
            'Ns': int(engine.Ns),
            'grid_spacing_m': float(engine.h),
            'time_step_s': float(engine.Ts),
            'sound_speed_m_s': float(engine.c),
            'courant': float(engine.l),
        },
        'measurements': {
            'setup_s': setup_s,
            'engine_prepare_s': prepare_s,
            'solve_s': solve_s,
            'save_s': save_s,
            'peak_ram_mb': peak_ram_mb,
            'generated_files_mb': _directory_size_mb(sim_dir),
            'sim_outs_mb': output_path.stat().st_size / (1024.0 * 1024.0),
        },
        'output_verification': {
            'shape': list(output.shape),
            'max_abs': max_abs,
            'nonzero_samples': nonzero_samples,
            'finite': True,
        },
        'diagnostics': [
            'The smoke uses R100A geometry/source/receiver authority but does not evaluate the analytical eigenfrequency observables.',
            'PFFDTD derives its simulation sound speed from temperature/humidity; the computed value is recorded instead of being silently treated as the R100A 343 m/s comparison authority.',
            'Three exact-source-checked runtime compatibility patches are applied and recorded; no FDTD or voxel numerical algorithm is changed.',
            'Successful source-checkout execution is not a Windows product packaging PASS and is not a CPU correctness baseline PASS.',
        ],
    }


def _write_artifact(
    output: Path,
    benchmark,
    candidates,
    *,
    outcome: str,
    details: dict[str, object] | None,
    error: str | None,
) -> None:
    evidence_ref = f'artifact:{output.as_posix()}'
    diagnostic = error or 'Pinned PFFDTD Python/Numba CPU smoke executed and produced finite non-zero output.'
    run = _make_run(benchmark, candidates, evidence_ref, outcome, diagnostic)
    payload = {
        'schema_version': PROBE_SCHEMA,
        'probe_id': PROBE_ID,
        'probe_outcome': outcome,
        'r100a_manifest_id': benchmark.manifest_id,
        'r100a_semantic_hash': benchmark.semantic_hash(),
        'candidate_manifest_hash': candidates.semantic_hash(),
        'details': details,
        'error': error,
        'bakeoff_run': run.model_dump(mode='json'),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run the R100B PFFDTD Windows Python/Numba smoke probe')
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--candidates', required=True, type=Path)
    parser.add_argument('--upstream-root', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    benchmark = load_acoustic_benchmark_manifest(args.manifest)
    candidates = load_bakeoff_candidate_manifest(args.candidates)
    outcome = 'pass'
    details: dict[str, object] | None = None
    error: str | None = None
    try:
        details = _execute(args.upstream_root, args.work_dir, benchmark, candidates)
    except Exception as exc:
        outcome = 'fail'
        error = f'{type(exc).__name__}: {exc}'
        details = {
            'traceback': traceback.format_exc(),
            'runtime_versions': _runtime_versions(),
            'upstream_root': str(args.upstream_root),
        }

    _write_artifact(
        args.output,
        benchmark,
        candidates,
        outcome=outcome,
        details=details,
        error=error,
    )
    print(
        json.dumps(
            {
                'probe_id': PROBE_ID,
                'probe_outcome': outcome,
                'output': str(args.output),
                'error': error,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
