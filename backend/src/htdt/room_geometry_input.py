from __future__ import annotations

from math import hypot
from uuid import uuid4

import numpy as np
import pyvista as pv
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from .cad_scene import RoomVertex, make_polygon_room, room_vertices
from .room_viewport import RoomViewport3D
from .room_workspace import RoomWorkspace


class RoomGeometryInputController(QObject):
    """Direct-manipulation polygon-room tool for the UX120 viewport.

    The controller owns only transient pointer state. Valid room snapshots are
    committed through RoomWorkspaceController -> RoomWorkingDocument so Undo,
    recovery and SceneRevision semantics remain authoritative there.
    """

    def __init__(self, workspace: RoomWorkspace, viewport: RoomViewport3D) -> None:
        super().__init__(workspace)
        self.workspace = workspace
        self.viewport = viewport
        self.mode = "idle"
        self._sketch: list[RoomVertex] = []
        self._cursor: tuple[float, float] | None = None
        self._drag_index: int | None = None
        self._drag_base: tuple[RoomVertex, ...] = ()
        self._drag_preview: tuple[RoomVertex, ...] = ()
        viewport.interactor.installEventFilter(self)

    @property
    def is_active(self) -> bool:
        return self.mode != "idle"

    def dispose(self) -> None:
        try:
            self.viewport.interactor.removeEventFilter(self)
        except RuntimeError:
            pass
        self._clear_overlays()
        self.mode = "idle"

    def start_sketch(self) -> None:
        if self.workspace.controller.recovery_candidate is not None:
            self.workspace._set_status("復旧データを処理してから部屋を描いてください", error=True)
            return
        if self.workspace.controller.working.has_preview:
            self.workspace.controller.working.cancel_preview()
        self.workspace.select_entity(None)
        self.mode = "sketch"
        self._sketch = []
        self._cursor = None
        self._drag_index = None
        self._drag_base = ()
        self._drag_preview = ()
        self._view_top()
        self._render_sketch()
        self.workspace._set_status(
            "部屋を描画中 · 頂点をクリック · 最初の頂点または Enter で閉じる · Esc で中止"
        )

    def start_edit(self) -> None:
        room = self.workspace.controller.document.room
        if room is None:
            self.workspace._set_status("先に部屋を描いてください", error=True)
            return
        if self.workspace.controller.recovery_candidate is not None:
            self.workspace._set_status("復旧データを処理してから形状を編集してください", error=True)
            return
        self.workspace.select_entity(None)
        self.mode = "edit"
        self._sketch = []
        self._cursor = None
        self._drag_index = None
        self._drag_base = ()
        self._drag_preview = ()
        self._view_top()
        self._render_edit_handles()
        self.workspace._set_status("形状編集中 · 頂点をドラッグ · Enter で終了 · Esc で終了")

    def commit(self) -> bool:
        if self.mode == "sketch":
            return self._close_sketch()
        if self.mode == "edit":
            self._finish()
            return True
        return False

    def cancel(self) -> bool:
        if self.mode == "idle":
            return False
        self._finish()
        self.workspace._set_status("形状編集を終了しました")
        return True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self.viewport.interactor or self.mode == "idle":
            return False
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress:
            return self._mouse_press(event)  # type: ignore[arg-type]
        if event_type == QEvent.Type.MouseMove:
            return self._mouse_move(event)  # type: ignore[arg-type]
        if event_type == QEvent.Type.MouseButtonRelease:
            return self._mouse_release(event)  # type: ignore[arg-type]
        return False

    def _mouse_press(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        position = QPointF(event.position())
        if self.mode == "sketch":
            floor = self._screen_to_floor(position)
            if floor is None:
                return False
            if len(self._sketch) >= 3 and self._near_first(position):
                self._close_sketch()
            else:
                x_m, y_m = floor
                self._sketch.append(
                    RoomVertex(
                        vertex_id=f"room-v-{uuid4().hex[:12]}",
                        x_m=x_m,
                        y_m=y_m,
                    )
                )
                self._render_sketch()
            event.accept()
            return True

        hit = self._hit_vertex(position)
        if hit is None:
            return False
        self._drag_index = hit
        self._drag_base = tuple(room_vertices(self.workspace.controller.document.room))
        self._drag_preview = self._drag_base
        event.accept()
        return True

    def _mouse_move(self, event: QMouseEvent) -> bool:
        position = QPointF(event.position())
        if self.mode == "sketch":
            floor = self._screen_to_floor(position)
            if floor is not None:
                self._cursor = floor
                self._render_sketch()
            return False

        if self._drag_index is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        floor = self._screen_to_floor(position)
        if floor is None:
            return True
        x_m, y_m = floor
        vertices = list(self._drag_base)
        original = vertices[self._drag_index]
        vertices[self._drag_index] = RoomVertex(
            vertex_id=original.vertex_id,
            x_m=x_m,
            y_m=y_m,
        )
        self._drag_preview = tuple(vertices)
        self._render_edit_handles(self._drag_preview)
        event.accept()
        return True

    def _mouse_release(self, event: QMouseEvent) -> bool:
        if (
            self.mode != "edit"
            or event.button() != Qt.MouseButton.LeftButton
            or self._drag_index is None
        ):
            return False
        self._commit_drag()
        event.accept()
        return True

    def _close_sketch(self) -> bool:
        if len(self._sketch) < 3:
            self.workspace._set_status("部屋には3頂点以上が必要です", error=True)
            return False
        current = self.workspace.controller.document.room
        height_m = 2.4 if current is None else current.height_m
        try:
            room = make_polygon_room(tuple(self._sketch), height_m=height_m)
            changed = self.workspace.controller.replace_room(room)
        except ValueError as exc:
            self.workspace._set_status(f"部屋形状を確定できません: {exc}", error=True)
            return False
        self.mode = "edit"
        self._sketch = []
        self._cursor = None
        self.workspace.refresh(reset_camera=False)
        self._render_edit_handles()
        self.workspace._set_status(
            "部屋を作成しました · 頂点をドラッグして調整 · Enter で終了"
            if changed
            else "部屋形状は変更されていません"
        )
        return changed

    def _commit_drag(self) -> None:
        room = self.workspace.controller.document.room
        preview = self._drag_preview
        self._drag_index = None
        self._drag_base = ()
        self._drag_preview = ()
        if room is None or not preview:
            self._render_edit_handles()
            return
        try:
            replacement = make_polygon_room(
                preview,
                height_m=room.height_m,
                room_id=room.room_id,
            )
            changed = self.workspace.controller.replace_room(replacement)
        except ValueError as exc:
            self.workspace._set_status(f"頂点移動を適用できません: {exc}", error=True)
            self.workspace.refresh()
            self._render_edit_handles()
            return
        self.workspace.refresh()
        self._render_edit_handles()
        if changed:
            self.workspace._set_status("頂点を移動しました · 元に戻す で復元できます")

    def _finish(self) -> None:
        self.mode = "idle"
        self._sketch = []
        self._cursor = None
        self._drag_index = None
        self._drag_base = ()
        self._drag_preview = ()
        self._clear_overlays()
        self.workspace.refresh()

    def _view_top(self) -> None:
        plotter = self.viewport.plotter
        plotter.view_xy(negative=True)
        plotter.enable_parallel_projection()
        plotter.reset_camera()
        plotter.render()

    def _screen_to_floor(self, position: QPointF) -> tuple[float, float] | None:
        renderer = self.viewport.plotter.renderer
        dpr = max(float(self.viewport.interactor.devicePixelRatioF()), 1.0)
        _, render_height = self.viewport.plotter.render_window.GetSize()
        display_x = float(position.x()) * dpr
        display_y = float(render_height) - float(position.y()) * dpr

        def world(depth: float) -> np.ndarray | None:
            renderer.SetDisplayPoint(display_x, display_y, depth)
            renderer.DisplayToWorld()
            x, y, z, w = renderer.GetWorldPoint()
            if abs(float(w)) <= 1e-12:
                return None
            return np.asarray((x / w, y / w, z / w), dtype=float)

        near = world(0.0)
        far = world(1.0)
        if near is None or far is None:
            return None
        ray = far - near
        if abs(float(ray[2])) <= 1e-12:
            return None
        fraction = -float(near[2]) / float(ray[2])
        point = near + ray * fraction
        return float(point[0]), -float(point[1])

    def _project(self, vertex: RoomVertex) -> QPointF:
        renderer = self.viewport.plotter.renderer
        renderer.SetWorldPoint(float(vertex.x_m), -float(vertex.y_m), 0.0, 1.0)
        renderer.WorldToDisplay()
        x, y, _ = renderer.GetDisplayPoint()
        dpr = max(float(self.viewport.interactor.devicePixelRatioF()), 1.0)
        _, render_height = self.viewport.plotter.render_window.GetSize()
        return QPointF(float(x) / dpr, (float(render_height) - float(y)) / dpr)

    def _near_first(self, position: QPointF) -> bool:
        if not self._sketch:
            return False
        point = self._project(self._sketch[0])
        return hypot(position.x() - point.x(), position.y() - point.y()) <= 12.0

    def _hit_vertex(self, position: QPointF) -> int | None:
        room = self.workspace.controller.document.room
        if room is None:
            return None
        hits: list[tuple[float, int]] = []
        for index, vertex in enumerate(room_vertices(room)):
            point = self._project(vertex)
            distance = hypot(position.x() - point.x(), position.y() - point.y())
            if distance <= 12.0:
                hits.append((distance, index))
        return None if not hits else min(hits)[1]

    def _clear_overlays(self) -> None:
        for name in (
            "ux120-room-sketch-line",
            "ux120-room-sketch-points",
            "ux120-room-sketch-cursor",
            "ux120-room-edit-line",
            "ux120-room-edit-points",
        ):
            self.viewport.plotter.remove_actor(name, reset_camera=False, render=False)
        self.viewport.plotter.render()

    def _render_sketch(self) -> None:
        self._clear_overlays()
        vertices = tuple(self._sketch)
        if len(vertices) >= 2:
            points = np.asarray([(v.x_m, -v.y_m, 0.0) for v in vertices], dtype=float)
            self.viewport.plotter.add_mesh(
                pv.lines_from_points(points, close=False),
                line_width=3,
                pickable=False,
                name="ux120-room-sketch-line",
                render=False,
            )
        if vertices:
            points = np.asarray([(v.x_m, -v.y_m, 0.0) for v in vertices], dtype=float)
            self.viewport.plotter.add_mesh(
                pv.PolyData(points),
                render_points_as_spheres=True,
                point_size=12,
                pickable=False,
                name="ux120-room-sketch-points",
                render=False,
            )
        if vertices and self._cursor is not None:
            x_m, y_m = self._cursor
            self.viewport.plotter.add_mesh(
                pv.Line(
                    (vertices[-1].x_m, -vertices[-1].y_m, 0.0),
                    (x_m, -y_m, 0.0),
                ),
                line_width=2,
                pickable=False,
                name="ux120-room-sketch-cursor",
                render=False,
            )
        self.viewport.plotter.render()

    def _render_edit_handles(self, vertices: tuple[RoomVertex, ...] | None = None) -> None:
        self._clear_overlays()
        room = self.workspace.controller.document.room
        if room is None:
            return
        values = vertices or tuple(room_vertices(room))
        if len(values) >= 2:
            points = np.asarray(
                [(v.x_m, -v.y_m, 0.0) for v in (*values, values[0])],
                dtype=float,
            )
            self.viewport.plotter.add_mesh(
                pv.lines_from_points(points, close=False),
                line_width=3,
                pickable=False,
                name="ux120-room-edit-line",
                render=False,
            )
        points = np.asarray([(v.x_m, -v.y_m, 0.0) for v in values], dtype=float)
        self.viewport.plotter.add_mesh(
            pv.PolyData(points),
            render_points_as_spheres=True,
            point_size=13,
            pickable=False,
            name="ux120-room-edit-points",
            render=False,
        )
        self.viewport.plotter.render()


__all__ = ["RoomGeometryInputController"]
