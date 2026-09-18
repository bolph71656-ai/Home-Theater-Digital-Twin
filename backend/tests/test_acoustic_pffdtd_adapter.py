from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from htdt.acoustic_benchmark import load_acoustic_benchmark_manifest
from htdt.acoustic_pffdtd_adapter import (
    compile_rigid_fixture_model,
    recombine_pffdtd_receiver_traces,
    pffdtd_velocity_potential_to_pressure_transfer,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / 'benchmarks' / 'acoustics' / 'r100a_manifest.json'


def _fixture():
    manifest = load_acoustic_benchmark_manifest(MANIFEST_PATH)
    return next(
        item
        for item in manifest.fixtures
        if item.fixture_id == 'wave-rigid-rectangular-modes-v1'
    )


def test_rigid_fixture_compiler_preserves_box_authority_and_outward_triangles() -> None:
    fixture = _fixture()
    model = compile_rigid_fixture_model(fixture)
    rigid = model['mats_hash']['_RIGID']

    points = np.asarray(rigid['pts'], dtype=np.float64)
    triangles = np.asarray(rigid['tris'], dtype=np.int64)
    room_centroid = points.mean(axis=0)

    assert points.shape == (8, 3)
    assert triangles.shape == (12, 3)
    assert np.allclose(points.min(axis=0), [0.0, 0.0, 0.0])
    assert np.allclose(points.max(axis=0), [4.0, 5.0, 2.5])
    assert model['sources'][0]['xyz'] == [1.0, 1.0, 1.0]
    assert model['receivers'][0]['xyz'] == [3.0, 3.0, 1.2]

    for tri in triangles:
        vertices = points[tri]
        normal = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
        triangle_centroid = vertices.mean(axis=0)
        assert float(np.dot(normal, triangle_centroid - room_centroid)) > 0.0


def test_receiver_recombination_matches_upstream_trilinear_contract() -> None:
    raw = np.arange(24, dtype=np.float64).reshape(8, 3)
    weights = np.asarray([[0.1, 0.1, 0.1, 0.1, 0.15, 0.15, 0.15, 0.15]])
    expected = np.sum(
        (raw * weights.flat[:][:, None]).reshape((*weights.shape, -1)),
        axis=1,
    )

    actual = recombine_pffdtd_receiver_traces(
        raw,
        weights,
        receiver_count=1,
        nt=3,
    )

    assert actual.shape == (1, 3)
    assert np.allclose(actual, expected)


def test_receiver_recombination_rejects_authority_mismatch() -> None:
    with pytest.raises(ValueError, match='mismatch'):
        recombine_pffdtd_receiver_traces(
            np.zeros((7, 3), dtype=np.float64),
            np.zeros((1, 8), dtype=np.float64),
            receiver_count=1,
            nt=3,
        )


def test_velocity_potential_pressure_transfer_uses_exp_minus_iwt_authority() -> None:
    source = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    potential = 2.0 * source
    frequencies = np.asarray([100.0, 200.0], dtype=np.float64)

    actual = pffdtd_velocity_potential_to_pressure_transfer(
        potential,
        source,
        time_step_s=0.001,
        frequency_hz=frequencies,
        density_kg_m3=1.2,
    )

    expected = -1j * 2.0 * np.pi * frequencies * 1.2 * 2.0
    assert np.allclose(actual, expected)


def test_velocity_potential_pressure_transfer_rejects_zero_source_spectrum() -> None:
    with pytest.raises(ValueError, match='source spectrum is zero'):
        pffdtd_velocity_potential_to_pressure_transfer(
            np.ones(4, dtype=np.float64),
            np.zeros(4, dtype=np.float64),
            time_step_s=0.001,
            frequency_hz=np.asarray([100.0]),
            density_kg_m3=1.2,
        )
