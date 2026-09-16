import pytest

from htdt.cad_scene import Position3, make_f1_scene
from htdt.cad_snap import (
    SnapCandidate, SnapSelector, generate_snap_candidates,
    snap_angle_deg, snap_position_axis, snap_scalar,
)


def test_snap_scalar_uses_half_away_from_zero() -> None:
    assert snap_scalar(0.125, 0.05) == pytest.approx(0.15)
    assert snap_scalar(-0.125, 0.05) == pytest.approx(-0.15)


def test_grid_snap_changes_only_active_world_axis() -> None:
    original = Position3(x_m=1.234, y_m=2.345, z_m=0.987)
    snapped = snap_position_axis(original, 'y', 0.05)
    assert snapped.x_m == original.x_m
    assert snapped.y_m == pytest.approx(2.35)
    assert snapped.z_m == original.z_m


def test_angle_snap_is_independent_from_grid_step() -> None:
    assert snap_angle_deg(22.4, 15.0) == pytest.approx(15.0)
    assert snap_angle_deg(22.6, 15.0) == pytest.approx(30.0)


def test_invalid_snap_steps_are_rejected() -> None:
    with pytest.raises(ValueError):
        snap_scalar(1.0, 0.0)
    with pytest.raises(ValueError):
        snap_angle_deg(10.0, float('nan'))


def test_geometric_candidates_exclude_moving_selection_and_have_stable_feature_ids() -> None:
    candidates = generate_snap_candidates(
        make_f1_scene(),
        exclude_ids={'speaker-fl', 'speaker-c'},
        axis='x',
        probe=Position3(x_m=1.8, y_m=0.75, z_m=1.05),
    )
    assert candidates
    assert all(candidate.entity_id not in {'speaker-fl', 'speaker-c'} for candidate in candidates)
    assert {'vertex', 'midpoint', 'edge', 'alignment'} <= {candidate.kind for candidate in candidates}
    stable_ids = [candidate.stable_id for candidate in candidates]
    assert len(stable_ids) == len(set(stable_ids))


def _snap_candidate(stable_id: str, kind: str, x_m: float) -> SnapCandidate:
    return SnapCandidate(
        stable_id=stable_id,
        kind=kind,  # type: ignore[arg-type]
        entity_id='target',
        target=Position3(x_m=x_m, y_m=0.0, z_m=0.0),
        screen_anchor=Position3(x_m=x_m, y_m=0.0, z_m=0.0),
        axis='x',
        label=stable_id,
    )


def test_screen_space_snap_uses_acquire_retain_hysteresis() -> None:
    selector = SnapSelector(acquire_radius_dip=8.0, retain_radius_dip=12.0)
    candidates = (_snap_candidate('a', 'vertex', 1.0), _snap_candidate('b', 'vertex', 1.5))
    project = lambda position: (position.x_m * 10.0, 0.0)

    first = selector.select(candidates, Position3(x_m=1.05, y_m=0.0, z_m=0.0), project)
    assert first is not None and first.candidate.stable_id == 'a'
    retained = selector.select(candidates, Position3(x_m=1.9, y_m=0.0, z_m=0.0), project)
    assert retained is not None and retained.candidate.stable_id == 'a'
    switched = selector.select(candidates, Position3(x_m=2.3, y_m=0.0, z_m=0.0), project)
    assert switched is not None and switched.candidate.stable_id == 'b'


def test_snap_priority_precedes_distance_and_stable_id_breaks_ties() -> None:
    selector = SnapSelector()
    project = lambda position: (position.x_m * 10.0, 0.0)
    probe = Position3(x_m=1.0, y_m=0.0, z_m=0.0)
    priority_candidates = (
        _snap_candidate('alignment-near', 'alignment', 1.1),
        _snap_candidate('vertex-farther', 'vertex', 1.6),
    )
    selected = selector.select(priority_candidates, probe, project)
    assert selected is not None and selected.candidate.stable_id == 'vertex-farther'

    selector.reset()
    tie_candidates = (
        _snap_candidate('b', 'vertex', 1.4),
        _snap_candidate('a', 'vertex', 1.4),
    )
    tied = selector.select(tie_candidates, probe, project)
    assert tied is not None and tied.candidate.stable_id == 'a'


def test_snap_selector_rejects_invalid_radii() -> None:
    with pytest.raises(ValueError):
        SnapSelector(acquire_radius_dip=0.0, retain_radius_dip=12.0)
    with pytest.raises(ValueError):
        SnapSelector(acquire_radius_dip=12.0, retain_radius_dip=8.0)
