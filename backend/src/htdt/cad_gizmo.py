from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pyvista as pv


MatrixCallback = Callable[[np.ndarray], None]


class TranslationWidget3D:
    """Three-axis translation-only widget for HTDT's left-handed domain axes."""

    def __init__(
        self,
        plotter: pv.Plotter,
        actor: pv.Actor,
        *,
        interact_callback: MatrixCallback | None = None,
        release_callback: MatrixCallback | None = None,
    ) -> None:
        self.plotter = plotter
        self.actor = actor
        self.interact_callback = interact_callback
        self.release_callback = release_callback
        self.axes = np.array(((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)))
        self.origin = np.asarray(actor.center, dtype=float)
        self.actor_length = max(float(actor.GetLength()), 0.25)
        self.handles: list[pv.Actor] = []
        self.selected: pv.Actor | None = None
        self.initial_world: np.ndarray | None = None
        self.pressing = False
        self.matrix = np.eye(4)
        self.observers: list[int] = []
        colors = (
            pv.global_theme.axes.x_color,
            pv.global_theme.axes.y_color,
            pv.global_theme.axes.z_color,
        )
        for axis, color in zip(self.axes, colors, strict=True):
            handle = plotter.add_mesh(
                pv.Arrow(start=self.origin, direction=axis, scale=self.actor_length * 0.75),
                color=color,
                lighting=False,
                pickable=True,
                render=False,
            )
            handle.mapper.SetResolveCoincidentTopologyToPolygonOffset()
            handle.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(0, -20000)
            self.handles.append(handle)
        self.observers.extend(
            (
                plotter.iren.add_observer('MouseMoveEvent', self._move),
                plotter.iren.add_observer('LeftButtonPressEvent', self._press, interactor_style_fallback=False),
                plotter.iren.add_observer('LeftButtonReleaseEvent', self._release, interactor_style_fallback=False),
            )
        )
        plotter.render()

    def _world_for_translation(self, interactor) -> np.ndarray:
        x, y = interactor.GetEventPosition()
        renderer = self.plotter.iren.get_poked_renderer()
        width, height = renderer.GetSize()
        ndc = np.array((2 * x / width - 1, 2 * y / height - 1, 1.0, 1.0))
        camera = renderer.GetActiveCamera()
        projection = pv.array_from_vtkmatrix(
            camera.GetProjectionTransformMatrix(renderer.GetTiledAspectRatio(), 0, 1)
        )
        camera_coords = np.linalg.inv(projection) @ ndc
        modelview = pv.array_from_vtkmatrix(camera.GetModelViewTransformMatrix())
        world = np.linalg.inv(modelview) @ camera_coords
        return world[:3] * self.actor_length * 2

    def _pick_handle(self, interactor) -> pv.Actor | None:
        x, y = interactor.GetEventPosition()
        renderer = self.plotter.iren.get_poked_renderer()
        picker = interactor.GetPicker()
        picker.Pick(x, y, 0, renderer)
        picked = picker.GetActor()
        return picked if picked in self.handles else None

    def _move(self, interactor, _event) -> None:
        if self.pressing and self.selected is not None and self.initial_world is not None:
            current = self._world_for_translation(interactor)
            axis = self.axes[self.handles.index(self.selected)]
            delta = axis * float(np.dot(current - self.initial_world, axis))
            self.matrix = np.eye(4)
            self.matrix[:3, 3] = delta
            self.actor.user_matrix = self.matrix
            if self.interact_callback:
                self.interact_callback(self.matrix.copy())
            self.plotter.render()
            return
        self.selected = self._pick_handle(interactor)

    def _press(self, interactor, _event) -> None:
        self.selected = self._pick_handle(interactor)
        if self.selected is None:
            return
        self.plotter.enable_trackball_actor_style()
        self.initial_world = self._world_for_translation(interactor)
        self.pressing = True

    def _release(self, _interactor, _event) -> None:
        if not self.pressing:
            return
        self.plotter.enable_trackball_style()
        self.pressing = False
        if self.release_callback:
            self.release_callback(self.matrix.copy())

    def cancel(self) -> None:
        self.actor.user_matrix = np.eye(4)
        self.matrix = np.eye(4)
        self.pressing = False
        self.initial_world = None
        self.plotter.enable_trackball_style()
        self.plotter.render()

    def remove(self) -> None:
        for observer in self.observers:
            self.plotter.iren.remove_observer(observer)
        self.observers.clear()
        for handle in self.handles:
            self.plotter.remove_actor(handle, render=False)
        self.handles.clear()
