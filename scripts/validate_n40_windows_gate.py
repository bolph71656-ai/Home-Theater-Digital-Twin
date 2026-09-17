from __future__ import annotations

import sys

import validate_n40_windows as base


def set_top_fixture_camera(window) -> None:
    renderer = window.viewport.renderer
    camera = renderer.GetActiveCamera()
    width, height = window.viewport.render_window.GetSize()
    aspect = max(float(width) / max(float(height), 1.0), 0.1)
    parallel_scale = max(2.35, 3.35 / aspect)
    camera.SetFocalPoint(3.0, -2.0, 0.0)
    camera.SetPosition(3.0, -2.0, 10.0)
    camera.SetViewUp(0.0, 1.0, 0.0)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(parallel_scale)
    renderer.ResetCameraClippingRange()
    window.viewport.render()
    print(
        'A10_CAMERA_FRAME',
        width,
        height,
        f'aspect={aspect:.3f}',
        f'scale={parallel_scale:.3f}',
        flush=True,
    )


base.set_top_fixture_camera = set_top_fixture_camera

if __name__ == '__main__':
    raise SystemExit(base.main())
