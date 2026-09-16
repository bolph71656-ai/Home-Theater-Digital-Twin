import pytest

from htdt.cad_scene import Position3
from htdt.cad_snap import snap_angle_deg, snap_position_axis, snap_scalar


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
