from __future__ import annotations

from pathlib import Path

import pytest

from htdt.acoustic_bakeoff import (
    BakeoffCandidateManifest,
    BakeoffDecision,
    BakeoffFixtureEvidence,
    BakeoffHardGateEvidence,
    BakeoffPlatform,
    BakeoffRun,
    applicable_fixture_ids,
    load_bakeoff_candidate_manifest,
    preflight_summary,
    validate_bakeoff_decision,
    validate_bakeoff_run,
)
from htdt.acoustic_benchmark import load_acoustic_benchmark_manifest


ROOT = Path(__file__).resolve().parents[2]
R100A_PATH = ROOT / 'benchmarks' / 'acoustics' / 'r100a_manifest.json'
CANDIDATE_PATH = ROOT / 'benchmarks' / 'acoustics' / 'r100b_candidates.json'


def _authorities():
    return (
        load_acoustic_benchmark_manifest(R100A_PATH),
        load_bakeoff_candidate_manifest(CANDIDATE_PATH),
    )


def _candidate(candidates: BakeoffCandidateManifest, candidate_id: str):
    return next(item for item in candidates.candidates if item.candidate_id == candidate_id)


def _not_run_fixture(fixture_id: str) -> BakeoffFixtureEvidence:
    return BakeoffFixtureEvidence(
        fixture_id=fixture_id,
        status='not_run',
        adapter_id='htdt-r100b-probe',
        adapter_version='0',
        backend_version='not-run',
        precision='float64',
        diagnostics=('probe not executed yet',),
    )


def _gates(categories: list[str], status: str = 'not_run'):
    return tuple(
        BakeoffHardGateEvidence(
            category=category,
            status=status,
            summary='not evaluated by this schema test',
        )
        for category in categories
    )


def _run(candidate_id: str, fixture_ids: tuple[str, ...]) -> BakeoffRun:
    benchmark, candidates = _authorities()
    candidate = _candidate(candidates, candidate_id)
    if candidate.evaluation_scope == 'shipping_candidate':
        categories = [
            'physics_correctness',
            'cpu_baseline',
            'windows_packaging',
            'license_redistribution',
            'required_capability',
            'reproducible_authority',
        ]
    else:
        categories = ['physics_correctness', 'reproducible_authority']

    return BakeoffRun(
        run_id=f'test-{candidate_id}',
        r100a_manifest_id=benchmark.manifest_id,
        r100a_semantic_hash=benchmark.semantic_hash(),
        candidate_manifest_hash=candidates.semantic_hash(),
        candidate_id=candidate.candidate_id,
        candidate_source_commit_sha=candidate.source_commit_sha,
        platform=BakeoffPlatform(
            os='GitHub Actions Windows',
            architecture='x86_64',
            python_version='3.12',
            cpu='CI runner',
            logical_threads=4,
            thread_budget=4,
            gpu=None,
            device_notes='schema fixture only',
        ),
        fixture_evidence=tuple(_not_run_fixture(item) for item in fixture_ids),
        hard_gates=_gates(categories),
    )


def test_candidate_manifest_is_version_pinned_and_covers_primary_roles() -> None:
    benchmark, candidates = _authorities()

    assert candidates.schema_version == 'r100b-candidates-1'
    assert {item.role for item in candidates.candidates} == {
        'wave_primary_evaluation',
        'wave_reference',
        'geometric_reference',
    }

    pffdtd = _candidate(candidates, 'pffdtd-main-aa319f6')
    assert pffdtd.source_commit_sha == 'aa319f6c86517cb95aabfae8656277da62c3ead5'
    assert pffdtd.windows_packaging_status == 'linux_upstream_port_required'

    mfem = _candidate(candidates, 'mfem-v4.10-d964264')
    assert mfem.source_ref == 'v4.10'
    assert mfem.source_commit_sha == 'd964264cdb9a13e94a201b6c236c7721e0c8765f'

    pyroom = _candidate(candidates, 'pyroomacoustics-v0.10.1-f02b01d')
    assert pyroom.source_ref == 'v0.10.1'
    assert pyroom.evaluation_scope == 'reference_only'

    summary = preflight_summary(benchmark, candidates)
    assert set(summary['uncovered_fixture_ids']) == {
        'wave-portal-split-room-v1',
        'hybrid-overlap-continuity-v1',
    }


def test_probe_capabilities_are_not_accepted_capabilities() -> None:
    benchmark, candidates = _authorities()
    pffdtd = _candidate(candidates, 'pffdtd-main-aa319f6')

    applicable = set(applicable_fixture_ids(benchmark, pffdtd))
    assert 'wave-rigid-rectangular-modes-v1' in applicable
    assert 'wave-normal-incidence-impedance-v1' in applicable
    assert 'wave-portal-split-room-v1' not in applicable

    run = _run(pffdtd.candidate_id, tuple(sorted(applicable)))
    validate_bakeoff_run(benchmark, candidates, run)

    assert all(item.status == 'not_run' for item in run.fixture_evidence)
    assert all(item.status == 'not_run' for item in run.hard_gates)


def test_r100a_semantic_hash_mismatch_is_rejected() -> None:
    benchmark, candidates = _authorities()
    pffdtd = _candidate(candidates, 'pffdtd-main-aa319f6')
    run = _run(pffdtd.candidate_id, ('wave-rigid-rectangular-modes-v1',))
    payload = run.model_dump(mode='python')
    payload['r100a_semantic_hash'] = '0' * 64

    altered = BakeoffRun.model_validate(payload)
    with pytest.raises(ValueError, match='semantic hash'):
        validate_bakeoff_run(benchmark, candidates, altered)


def test_unknown_fixture_evidence_is_rejected() -> None:
    benchmark, candidates = _authorities()
    pffdtd = _candidate(candidates, 'pffdtd-main-aa319f6')
    run = _run(pffdtd.candidate_id, ('wave-rigid-rectangular-modes-v1',))
    payload = run.model_dump(mode='python')
    payload['fixture_evidence'][0]['fixture_id'] = 'not-an-r100a-fixture'

    altered = BakeoffRun.model_validate(payload)
    with pytest.raises(ValueError, match='unknown R100A fixture'):
        validate_bakeoff_run(benchmark, candidates, altered)


def test_candidate_cannot_execute_fixture_without_probe_capability() -> None:
    benchmark, candidates = _authorities()
    pffdtd = _candidate(candidates, 'pffdtd-main-aa319f6')
    run = _run(pffdtd.candidate_id, ('wave-portal-split-room-v1',))
    payload = run.model_dump(mode='python')
    payload['fixture_evidence'][0].update(
        status='fail',
        evidence_ref='artifacts/r100b/pffdtd/portal.json',
        backend_version='pffdtd-pinned',
        compile_s=1.0,
        solve_s=1.0,
        postprocess_s=1.0,
        peak_ram_mb=1.0,
        output_mb=1.0,
    )

    altered = BakeoffRun.model_validate(payload)
    with pytest.raises(ValueError, match='without all required probe capabilities'):
        validate_bakeoff_run(benchmark, candidates, altered)


def test_production_selection_is_blocked_until_hard_gates_and_fixtures_pass() -> None:
    benchmark, candidates = _authorities()
    pffdtd = _candidate(candidates, 'pffdtd-main-aa319f6')
    applicable = applicable_fixture_ids(benchmark, pffdtd)
    run = _run(pffdtd.candidate_id, applicable)

    decision = BakeoffDecision(
        status='selected',
        selected_candidate_id=pffdtd.candidate_id,
        accepted_run_id=run.run_id,
        rationale='schema guard test',
    )

    with pytest.raises(ValueError, match='hard gates'):
        validate_bakeoff_decision(benchmark, candidates, (run,), decision)


def test_reference_only_candidate_cannot_be_selected_for_production() -> None:
    benchmark, candidates = _authorities()
    pyroom = _candidate(candidates, 'pyroomacoustics-v0.10.1-f02b01d')
    run = _run(pyroom.candidate_id, applicable_fixture_ids(benchmark, pyroom))

    decision = BakeoffDecision(
        status='selected',
        selected_candidate_id=pyroom.candidate_id,
        accepted_run_id=run.run_id,
        rationale='schema guard test',
    )

    with pytest.raises(ValueError, match='reference-only'):
        validate_bakeoff_decision(benchmark, candidates, (run,), decision)
