from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from htdt.cad_repository import SceneRepository
from htdt.cad_scene import RoomVertex, make_empty_scene, room_vertices
from htdt.room_editor import RoomEditorWindow
from scripts.validate_n30a_windows import (
    F2_POINTS,
    domain_to_global,
    foreground_window,
    pump,
    set_top_fixture_camera,
    settled_click,
)

if sys.platform != 'win32':
    raise SystemExit('Windows only')

user32 = ctypes.windll.user32


class TraceRoomEditorWindow(RoomEditorWindow):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            watched is self.viewport.interactor
            and self.room_mode == 'edit'
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = event.position()
            vertices = self._room_vertices()
            midpoint = None
            projected = None
            if len(vertices) >= 2:
                a, b = vertices[0], vertices[1]
                midpoint = RoomVertex(
                    vertex_id='trace-mid',
                    x_m=(a.x_m + b.x_m) / 2.0,
                    y_m=(a.y_m + b.y_m) / 2.0,
                )
                projected = self._project_room_to_qt(midpoint)
            print(
                'TRACE_PRESS',
                'EVENT', (float(pos.x()), float(pos.y())),
                'PROJECTED', projected,
                'HIT', self._hit_room_handle(float(pos.x()), float(pos.y())),
                'CHECKED', self.insert_vertex_action.isChecked(),
                'MODE', self.room_mode,
                flush=True,
            )
        return super().eventFilter(watched, event)

    def _insert_room_vertex(self, edge_index: int) -> None:
        print('TRACE_INSERT_CALL', edge_index, flush=True)
        super()._insert_room_vertex(edge_index)


def main() -> int:
    app = QApplication.instance() or QApplication([sys.argv[0]])
    with tempfile.TemporaryDirectory(prefix='htdt-n30a-hit-') as temp:
        repo = SceneRepository(Path(temp) / 'scene.sqlite3')
        repo.save(make_empty_scene('diag-hit'), parent_revision_id=None)
        window = TraceRoomEditorWindow(repo, 'diag-hit')
        foreground_window(window, app)
        window.start_room_sketch()
        set_top_fixture_camera(window)
        foreground_window(window, app)
        for x_m, y_m in F2_POINTS:
            settled_click(domain_to_global(window, x_m, y_m), app)
            pump(app, 0.03)
        settled_click(domain_to_global(window, *F2_POINTS[0]), app)
        pump(app, 0.15)
        room = window.working.committed_document.room
        if room is None:
            print('TRACE_DRAW_FAILED', len(window.room_sketch_vertices), flush=True)
            window.close()
            return 2
        set_top_fixture_camera(window)
        window.insert_vertex_action.setChecked(True)
        vertices = room_vertices(room)
        a, b = vertices[0], vertices[1]
        midpoint = ((a.x_m + b.x_m) / 2.0, (a.y_m + b.y_m) / 2.0)
        point = domain_to_global(window, *midpoint)
        local = window.viewport.interactor.mapFromGlobal(point)
        print(
            'TRACE_BEFORE',
            'MID', midpoint,
            'LOCAL', (local.x(), local.y()),
            'PROJECTED', self_projected(window, a, b),
            'HIT', window._hit_room_handle(float(local.x()), float(local.y())),
            flush=True,
        )
        settled_click(point, app)
        pump(app, 0.15)
        after = window.working.committed_document.room
        print('TRACE_AFTER_COUNT', 0 if after is None else len(room_vertices(after)), 'SELECTED', window.selected_room_vertex_id, flush=True)
        window.close()
        pump(app, 0.1)
    return 0


def self_projected(window: RoomEditorWindow, a, b):
    midpoint = RoomVertex(
        vertex_id='trace-mid',
        x_m=(a.x_m + b.x_m) / 2.0,
        y_m=(a.y_m + b.y_m) / 2.0,
    )
    return window._project_room_to_qt(midpoint)


if __name__ == '__main__':
    raise SystemExit(main())
