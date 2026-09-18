from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyvista as pv
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

from .cad_scene import (
    SceneDocument,
    SceneEntity,
    acoustic_reference_position,
    domain_pose_to_render_matrix,
    domain_to_render,
    room_vertices,
)
from .ui_theme import DARK_THEME, SurfaceRole, set_surface_role


@dataclass(frozen=True, slots=True)
class RoomOverlayState:
    grid: bool = True
    labels: bool = False
    acoustics: bool = False
    focus_selection: bool = False


def _room_wireframe(document: SceneDocument) -> pv.PolyData | None:
    room = document.room
    if room is None:
        return None
    vertices = room_vertices(room)
    count = len(vertices)
    points = np.asarray(
        [(vertex.x_m, -vertex.y_m, 0.0) for vertex in vertices]
        + [(vertex.x_m, -vertex.y_m, room.height_m) for vertex in vertices],
        dtype=float,
    )
    lines: list[int] = []
    for offset in (0, count):
        for index in range(count):
            lines.extend((2, offset + index, offset + ((index + 1) % count)))
    for index in range(count):
        lines.extend((2, index, count + index))
    mesh = pv.PolyData(points)
    mesh.lines = np.asarray(lines, dtype=np.int64)
    return mesh


def _grid_mesh(document: SceneDocument, *, step_m: float = 0.5) -> pv.PolyData | None:
    room = document.room
    if room is None:
        return None
    min_x, min_y, max_x, max_y = room.bounds_m
    margin = max(step_m * 2.0, 0.5)
    x0 = np.floor((min_x - margin) / step_m) * step_m
    x1 = np.ceil((max_x + margin) / step_m) * step_m
    y0 = np.floor((min_y - margin) / step_m) * step_m
    y1 = np.ceil((max_y + margin) / step_m) * step_m
    points: list[tuple[float, float, float]] = []
    lines: list[int] = []

    def add_line(start: tuple[float, float, float], end: tuple[float, float, float]) -> None:
        index = len(points)
        points.extend((start, end))
        lines.extend((2, index, index + 1))

    for x_m in np.arange(x0, x1 + step_m * 0.5, step_m):
        add_line((float(x_m), float(-y0), 0.0), (float(x_m), float(-y1), 0.0))
    for y_m in np.arange(y0, y1 + step_m * 0.5, step_m):
        add_line((float(x0), float(-y_m), 0.0), (float(x1), float(-y_m), 0.0))
    mesh = pv.PolyData(np.asarray(points, dtype=float))
    mesh.lines = np.asarray(lines, dtype=np.int64)
    return mesh


def _entity_mesh(entity: SceneEntity) -> pv.PolyData:
    if entity.size_m is None:
        mesh = pv.Sphere(radius=0.08)
    else:
        mesh = pv.Cube(
            center=(0.0, 0.0, 0.0),
            x_length=entity.size_m.x_m,
            y_length=entity.size_m.y_m,
            z_length=entity.size_m.z_m,
        )
    mesh.transform(
        np.asarray(domain_pose_to_render_matrix(entity.position, entity.orientation), dtype=float),
        inplace=True,
    )
    return mesh


class RoomViewport3D(QFrame):
    """Dark, scene-authority-neutral viewport for the UX120 Room workspace.

    Camera navigation and keyboard shortcut policy are intentionally not owned here.
    Agent B can attach the CAD input controller to the public interactor attribute.
    """

    entitySelected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("roomViewport")
        set_surface_role(self, SurfaceRole.CANVAS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.plotter = QtInteractor(self)
        self.interactor = self.plotter.interactor
        layout.addWidget(self.interactor)

        self._actor_entity_ids: dict[int, str] = {}
        self._document: SceneDocument | None = None
        self._selected_id: str | None = None
        self._overlays = RoomOverlayState()
        self.plotter.set_background(DARK_THEME.viewport.background.hex)
        self.plotter.enable_anti_aliasing("fxaa")
        try:
            self.plotter.enable_mesh_picking(
                callback=self._picked_actor,
                show=False,
                show_message=False,
                left_clicking=True,
                use_actor=True,
            )
        except (TypeError, RuntimeError):
            # Picking is optional at this layer; Agent B may own selection input.
            pass

    def render_document(
        self,
        document: SceneDocument,
        *,
        selected_id: str | None,
        overlays: RoomOverlayState,
        reset_camera: bool = False,
    ) -> None:
        self._document = document
        self._selected_id = selected_id
        self._overlays = overlays
        self._actor_entity_ids.clear()
        self.plotter.clear()
        self.plotter.set_background(DARK_THEME.viewport.background.hex)

        if overlays.grid:
            grid = _grid_mesh(document)
            if grid is not None:
                self.plotter.add_mesh(
                    grid,
                    color=DARK_THEME.viewport.grid_minor.hex,
                    line_width=1,
                    opacity=0.55,
                    pickable=False,
                    name="room-grid",
                )

        room_mesh = _room_wireframe(document)
        if room_mesh is not None:
            self.plotter.add_mesh(
                room_mesh,
                color=DARK_THEME.viewport.geometry_edge.hex,
                line_width=2,
                opacity=0.62,
                pickable=False,
                name="room-shell",
            )

        for entity in document.entities:
            focused_out = bool(
                overlays.focus_selection
                and selected_id
                and entity.entity_id != selected_id
            )
            actor = self.plotter.add_mesh(
                _entity_mesh(entity),
                color=DARK_THEME.viewport.geometry.hex,
                show_edges=True,
                edge_color=(
                    DARK_THEME.viewport.selection_outline.hex
                    if entity.entity_id == selected_id
                    else DARK_THEME.viewport.geometry_edge.hex
                ),
                line_width=3 if entity.entity_id == selected_id else 1,
                opacity=0.10 if focused_out else 0.90,
                pickable=True,
                name=f"entity-{entity.entity_id}",
            )
            self._actor_entity_ids[id(actor)] = entity.entity_id

        if overlays.acoustics:
            self._render_acoustic_overlay(document)
        if overlays.labels:
            self._render_labels(document, selected_id)

        self.plotter.add_axes(
            color=DARK_THEME.text.muted.hex,
            line_width=1,
            labels_off=True,
        )
        if reset_camera:
            self.fit_scene()
        self.plotter.render()

    def _render_acoustic_overlay(self, document: SceneDocument) -> None:
        for entity in document.entities:
            reference = acoustic_reference_position(entity)
            if reference is not None:
                self.plotter.add_mesh(
                    pv.Sphere(radius=0.035, center=domain_to_render(reference)),
                    color=DARK_THEME.accent.primary.hex,
                    opacity=0.92,
                    pickable=False,
                    name=f"reference-{entity.entity_id}",
                )
            if entity.kind != "speaker" or entity.aim_xyz is None:
                continue
            origin = reference or entity.position
            end = type(origin)(
                x_m=origin.x_m + entity.aim_xyz.x * 1.2,
                y_m=origin.y_m + entity.aim_xyz.y * 1.2,
                z_m=origin.z_m + entity.aim_xyz.z * 1.2,
            )
            self.plotter.add_mesh(
                pv.Line(domain_to_render(origin), domain_to_render(end)),
                color=DARK_THEME.accent.primary.hex,
                line_width=2,
                opacity=0.80,
                pickable=False,
                name=f"aim-{entity.entity_id}",
            )

    def _render_labels(self, document: SceneDocument, selected_id: str | None) -> None:
        visible = [
            entity
            for entity in document.entities
            if (
                not self._overlays.focus_selection
                or selected_id is None
                or entity.entity_id == selected_id
            )
        ]
        if not visible:
            return
        self.plotter.add_point_labels(
            np.asarray([domain_to_render(entity.position) for entity in visible], dtype=float),
            [entity.name for entity in visible],
            text_color=DARK_THEME.text.primary.hex,
            shape_color=DARK_THEME.surfaces.overlay.hex,
            shape_opacity=0.88,
            font_size=12,
            point_size=0,
            always_visible=True,
            name="entity-labels",
        )

    def _picked_actor(self, actor) -> None:
        entity_id = self._actor_entity_ids.get(id(actor))
        if entity_id is not None:
            self.entitySelected.emit(entity_id)

    def fit_scene(self) -> None:
        self.plotter.reset_camera()
        self.plotter.camera.zoom(0.92)
        self.plotter.render()

    def focus_entity(self, entity_id: str) -> None:
        if self._document is None:
            return
        try:
            entity = self._document.entity(entity_id)
        except KeyError:
            return
        self.plotter.camera.focal_point = domain_to_render(entity.position)
        self.plotter.render()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.plotter.close()
        super().closeEvent(event)


__all__ = ["RoomOverlayState", "RoomViewport3D"]
