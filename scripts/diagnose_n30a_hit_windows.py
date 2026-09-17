from __future__ import annotations

import ctypes
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from htdt.cad_repository import SceneRepository
from htdt.cad_scene import make_empty_scene, room_vertices
from htdt.room_editor import RoomEditorWindow
from scripts.validate_n30a_windows import (
    F2_POINTS,
    click,
    domain_to_global,
    foreground_window,
    handle_to_global,
    midpoint_vertex,
    pump,
    set_top_fixture_camera,
)

if sys.platform != 'win32':
    raise SystemExit('Windows only')

user32 = ctypes.windll.user32
MOUSE_LEFTDOWN = 0x0002
MOUSE_LEFTUP = 0x0004


class TraceRoomEditorWindow(RoomEditorWindow):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.viewport.interactor and self.room_mode == 'edit':
            kind = event.type()
            pos = getattr(event, 'position', lambda: None)()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                print(
                    'TRACE_PRESS',
                    None if pos is None else (float(pos.x()), float(pos.y())),
                    'HIT', None if pos is None else self._hit_room_handle(float(pos.x()), float(pos.y())),
                    'INSERT', self.insert_vertex_action.isChecked(),
                    flush=True,
                )
            elif kind == QEvent.Type.MouseMove and self.room_drag_vertex_id is not None:
                floor = None if pos is None else self._screen_to_floor(float(pos.x()), float(pos.y()))
                print('TRACE_MOVE', None if pos is None else (float(pos.x()), float(pos.y())), 'FLOOR', floor, flush=True)
            elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                print('TRACE_RELEASE', 'DRAG_ID', self.room_drag_vertex_id, flush=True)
        result = super().eventFilter(watched, event)
        if watched is self.viewport.interactor and event.type() == QEvent.Type.MouseButtonPress:
            print('TRACE_AFTER_PRESS', 'DRAG_ID', self.room_drag_vertex_id, 'GRAB', QWidget.mouseGrabber() is self.viewport.interactor, flush=True)
        return result

    def _insert_room_vertex(self, edge_index: int) -> None:
        print('TRACE_INSERT_CALL', edge_index, flush=True)
        super()._insert_room_vertex(edge_index)

    def _commit_room_drag(self) -> None:
        print('TRACE_COMMIT_DRAG', 'ID', self.room_drag_vertex_id, 'PREVIEW', len(self.room_drag_preview), flush=True)
        super()._commit_room_drag()


def main() -> int:
    app = QApplication.instance() or QApplication([sys.argv[0]])
    with tempfile.TemporaryDirectory(prefix='htdt-n30a-drag-', ignore_cleanup_errors=True) as temp:
        repo = SceneRepository(Path(temp) / 'scene.sqlite3')
        repo.save(make_empty_scene('diag-drag'), parent_revision_id=None)
        window = TraceRoomEditorWindow(repo, 'diag-drag')
        foreground_window(window, app)
        window.start_room_sketch()
        set_top_fixture_camera(window)
        foreground_window(window, app)
        for x_m, y_m in F2_POINTS:
            click(domain_to_global(window, x_m, y_m), app, settle_s=0.08)
        click(domain_to_global(window, *F2_POINTS[0]), app, settle_s=0.08)
        pump(app, 0.15)

        room = window.working.committed_document.room
        if room is None:
            print('TRACE_DRAW_FAILED', flush=True)
            window.close()
            return 2

        set_top_fixture_camera(window)
        window.insert_vertex_action.setChecked(True)
        vertices = room_vertices(room)
        midpoint = midpoint_vertex(vertices[0], vertices[1])
        click(handle_to_global(window, midpoint), app, settle_s=0.10)
        pump(app, 0.12)
        window.insert_vertex_action.setChecked(False)
        room = window.working.committed_document.room
        inserted_id = window.selected_room_vertex_id
        inserted = None if room is None else next((v for v in room_vertices(room) if v.vertex_id == inserted_id), None)
        print('TRACE_INSERTED', inserted_id, inserted, flush=True)
        if inserted is None:
            window.close()
            return 3

        set_top_fixture_camera(window)
        start = handle_to_global(window, inserted)
        end = domain_to_global(window, 3.0, 0.5)
        print('TRACE_DRAG_TARGETS', (start.x(), start.y()), (end.x(), end.y()), flush=True)
        QCursor.setPos(start)
        pump(app, 0.12)
        user32.mouse_event(MOUSE_LEFTDOWN, 0, 0, 0, 0)
        pump(app, 0.08)
        print('TRACE_AFTER_DOWN_STATE', window.room_drag_vertex_id, QWidget.mouseGrabber() is window.viewport.interactor, flush=True)
        QCursor.setPos(end)
        pump(app, 0.15)
        print('TRACE_AFTER_MOVE_STATE', window.room_drag_vertex_id, len(window.room_drag_preview), flush=True)
        user32.mouse_event(MOUSE_LEFTUP, 0, 0, 0, 0)
        pump(app, 0.18)
        room = window.working.committed_document.room
        moved = None if room is None else next((v for v in room_vertices(room) if v.vertex_id == inserted_id), None)
        print('TRACE_FINAL', moved, 'HISTORY', window.working.history_length, flush=True)
        window.close()
        pump(app, 0.1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
