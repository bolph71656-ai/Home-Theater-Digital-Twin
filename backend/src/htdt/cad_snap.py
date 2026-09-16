from __future__ import annotations

from math import floor, isfinite
from typing import Literal

from .cad_scene import Position3


def _validate_step(step: float, *, label: str) -> float:
    step = float(step)
    if not isfinite(step) or step <= 0.0:
        raise ValueError(f'{label} must be a finite positive value')
    return step


def snap_scalar(value: float, step: float) -> float:
    """Round to the nearest step, with exact halves away from zero."""

    step = _validate_step(step, label='snap step')
    value = float(value)
    if not isfinite(value):
        raise ValueError('snap value must be finite')
    sign = -1.0 if value < 0.0 else 1.0
    return sign * floor(abs(value) / step + 0.5) * step


def snap_position_axis(position: Position3, axis: Literal['x', 'y', 'z'], step_m: float) -> Position3:
    """Snap only the actively constrained world axis; preserve the other coordinates."""

    step_m = _validate_step(step_m, label='grid step')
    values = {
        'x': position.x_m,
        'y': position.y_m,
        'z': position.z_m,
    }
    if axis not in values:
        raise ValueError(f'unsupported snap axis: {axis}')
    values[axis] = snap_scalar(values[axis], step_m)
    return Position3(x_m=values['x'], y_m=values['y'], z_m=values['z'])


def snap_angle_deg(angle_deg: float, step_deg: float) -> float:
    step_deg = _validate_step(step_deg, label='angle step')
    return snap_scalar(float(angle_deg), step_deg)
