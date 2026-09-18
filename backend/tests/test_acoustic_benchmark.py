from __future__ import annotations

from pathlib import Path

import pytest

from htdt.acoustic_benchmark import (
    AcousticBenchmarkFixture,
    AcousticBenchmarkManifest,
    AcousticMaterial,
    load_acoustic_benchmark_manifest,
)


MANIFEST_PATH = Path(__file__).resolve().parents[2] / 'benchmarks' / 'acoustics' / 'r100a_manifest.json'


def _manifest() -> AcousticBenchmarkManifest:
    return load_acoustic_benchmark_manifest(MANIFEST_PATH)


def _fixture(manifest: AcousticBenchmarkManifest, fixture_id: str) -> AcousticBenchmarkFixture:
    return next(item for item in manifest.fixtures if item.fixture_id == fixture_id)


def test_r100a_manifest_loads_as_immutable_canonical_authority() -> None:
    manifest = _manifest()

    assert manifest.schema_version == 'r100a-1'
    assert manifest.manifest_id == 'htdt-issue-101-r100a-benchmark-authority'
    assert manifest.revision == 1
    assert len(manifest.fixtures) == 10
    assert len(manifest.hard_gates) == 6
    assert len(manifest.semantic_hash()) == 64

    reparsed = AcousticBenchmarkManifest.model_validate_json(manifest.canonical_json())
    assert reparsed == manifest
    assert reparsed.semantic_hash() == manifest.semantic_hash()

    with pytest.raises(Exception):
        manifest.revision = 2  # type: ignore[misc]


def test_r100a_required_fixture_roles_are_present() -> None:
    manifest = _manifest()
    fixture_ids = {item.fixture_id for item in manifest.fixtures}

    assert {
        'wave-rigid-rectangular-modes-v1',
        'wave-rectangular-convergence-v1',
        'wave-normal-incidence-impedance-v1',
        'wave-concave-l-room-v1',
        'wave-portal-split-room-v1',
        'wave-explicit-radiation-termination-v1',
        'geometric-direct-first-reflection-v1',
        'geometric-reflecting-counter-v1',
        'geometric-seed-repeatability-v1',
        'hybrid-overlap-continuity-v1',
    } == fixture_ids


def test_opening_authority_is_explicit_portal_or_termination() -> None:
    manifest = _manifest()
    portal_fixture = _fixture(manifest, 'wave-portal-split-room-v1')
    termination_fixture = _fixture(manifest, 'wave-explicit-radiation-termination-v1')

    assert len(portal_fixture.regions) == 2
    assert len(portal_fixture.portals) == 1
    assert portal_fixture.portals[0].region_a_id == 'left'
    assert portal_fixture.portals[0].region_b_id == 'right'
    assert not portal_fixture.terminations

    assert len(termination_fixture.regions) == 1
    assert not termination_fixture.portals
    assert len(termination_fixture.terminations) == 1
    assert termination_fixture.terminations[0].kind == 'radiation'


def test_wave_impedance_capability_rejects_geometric_only_material() -> None:
    manifest = _manifest()
    fixture = _fixture(manifest, 'wave-normal-incidence-impedance-v1')
    payload = fixture.model_dump(mode='python')

    payload['materials'] = [
        item
        if item['material_id'] != 'z-2z0'
        else AcousticMaterial(
            material_id='z-2z0',
            provenance='deliberately insufficient geometric-only fixture',
            version='1',
            wave_model='unsupported',
            geometric_model='banded',
            geometric_bands=(
                {
                    'center_hz': 250.0,
                    'absorption': 0.5,
                    'scattering': 0.0,
                },
            ),
        ).model_dump(mode='python')
        for item in payload['materials']
    ]

    with pytest.raises(ValueError, match='phase-bearing impedance'):
        AcousticBenchmarkFixture.model_validate(payload)


def test_counter_fixture_has_explicit_acoustic_obstacle_and_peer_delta_contract() -> None:
    manifest = _manifest()
    counter = _fixture(manifest, 'geometric-reflecting-counter-v1')

    assert len(counter.obstacles) == 1
    obstacle = counter.obstacles[0]
    assert obstacle.obstacle_id == 'counter'
    assert obstacle.host_region_id == 'room'
    assert obstacle.representation == 'solid_volume'

    observable = counter.observables[0]
    assert observable.acceptance_relation == 'must_differ_from_peer'
    assert observable.peer_fixture_id == 'geometric-direct-first-reflection-v1'


def test_unknown_peer_fixture_is_rejected_fail_closed() -> None:
    manifest = _manifest()
    payload = manifest.model_dump(mode='python')
    counter = next(
        item for item in payload['fixtures'] if item['fixture_id'] == 'geometric-reflecting-counter-v1'
    )
    counter['observables'][0]['peer_fixture_id'] = 'missing-reference-fixture'

    with pytest.raises(ValueError, match='unknown peer fixtures'):
        AcousticBenchmarkManifest.model_validate(payload)
