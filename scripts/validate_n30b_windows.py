from __future__ import annotations

import argparse
import ctypes
import gc
from pathlib import Path
import sys
import tempfile
import time

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from htdt.cad_repository import SceneRepository
from htdt.cad_scene import F1_DOCUMENT_ID, RoomVertex, room_vertices
from htdt.wall_editor import WallEditorWindow

if sys.platform != 'win32':
    raise SystemExit('This acceptance harness requires Windows.')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='backslashreplace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='backslashreplace')

user32 = ctypes.windll.user32
MOUSE_LEFTDOWN = 0x0002
MOUSE_LEFTUP = 0x0004


def pump(app: QApplication, seconds: float = 0.05) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.002)


def foreground_window(window: WallEditorWindow, app: QApplication) -> None:
    window.show()
    window.showNormal()
    window.raise_()
    window.activateWindow()
    window.viewport.interactor.setFocus()
    user32.SetForegroundWindow(int(window.winId()))
    pump(app, 0.25)


def prepare_pointer(window: WallEditorWindow, app: QApplication) -> None:
    foreground_window(window, app)
    user32.mouse_event(MOUSE_LEFTUP, 0, 0, 0, 0)
    pump(app, 0.05)


def qt_global(window: WallEditorWindow, x_m: float, y_m: float) -> QPoint:
    qt_x, qt_y = window._project_xy_to_qt(x_m, y_m)
    return window.viewport.interactor.mapToGlobal(QPoint(int(round(qt_x)), int(round(qt_y))))


def click(window: WallEditorWindow, point: QPoint, app: QApplication) -> None:
    prepare_pointer(window, app)
    QCursor.setPos(point)
    pump(app, 0.12)
    user32.mouse_event(MOUSE_LEFTDOWN, 0, 0, 0, 0)
    pump(app, 0.06)
    user32.mouse_event(MOUSE_LEFTUP, 0, 0, 0, 0)
    pump(app, 0.12)


def drag(window: WallEditorWindow, start: QPoint, end: QPoint, app: QApplication) -> None:
    prepare_pointer(window, app)
    QCursor.setPos(start)
    pump(app, 0.12)
    user32.mouse_event(MOUSE_LEFTDOWN, 0, 0, 0, 0)
    pump(app, 0.10)
    QCursor.setPos(end)
    pump(app, 0.20)
    user32.mouse_event(MOUSE_LEFTUP, 0, 0, 0, 0)
    pump(app, 0.20)


def set_top_fixture_camera(window: WallEditorWindow) -> None:
    renderer = window.viewport.renderer
    camera = renderer.GetActiveCamera()
    camera.SetFocalPoint(3.0, -2.0, 0.0)
    camera.SetPosition(3.0, -2.0, 10.0)
    camera.SetViewUp(0.0, 1.0, 0.0)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(3.4)
    renderer.ResetCameraClippingRange()
    window.viewport.render()


def wall_midpoint(window: WallEditorWindow, wall_id: str) -> tuple[float, float]:
    room = window.working.committed_document.room
    topology = window.working.committed_document.wall_topology
    assert room is not None and topology is not None
    wall = next(wall for wall in topology.walls if wall.wall_id == wall_id)
    vertices = {vertex.vertex_id: vertex for vertex in room_vertices(room)}
    start = vertices[wall.from_vertex_id]
    end = vertices[wall.to_vertex_id]
    return ((start.x_m + end.x_m) / 2.0, (start.y_m + end.y_m) / 2.0)


def run_a09(app: QApplication, root: Path) -> bool:
    repository = SceneRepository(root / 'scene.sqlite3')
    window = WallEditorWindow(repository, F1_DOCUMENT_ID)
    foreground_window(window, app)
    try:
        japanese_ui_ok = (
            window.start_wall_action.text() == '壁を編集'
            and window.split_wall_action.text() == '壁を中央で分割'
            and window.add_clearance_action.text() == 'クリアランス参照を追加'
        )
        print('A09_JAPANESE_UI', japanese_ui_ok, flush=True)
        if not japanese_ui_ok:
            return False

        window.start_wall_edit()
        set_top_fixture_camera(window)
        topology = window.working.committed_document.wall_topology
        topology_ok = topology is not None and len(topology.walls) == 4
        print('A09_TOPOLOGY', topology_ok, flush=True)
        if not topology_ok or topology is None:
            return False

        front_wall_id = topology.walls[0].wall_id
        before_select = window.working.history_length
        midpoint = wall_midpoint(window, front_wall_id)
        click(window, qt_global(window, *midpoint), app)
        select_ok = window.selected_wall_id == front_wall_id and window.working.history_length == before_select
        print('A09_MOUSE_SELECT', select_ok, window.selected_wall_id, flush=True)
        if not select_ok:
            return False

        window.clearance_value.setValue(0.35)
        before_binding = window.working.history_length
        window.add_clearance_action.trigger()
        pump(app, 0.12)
        topology = window.working.committed_document.wall_topology
        binding_ok = (
            topology is not None
            and len(topology.constraint_bindings) == 1
            and topology.constraint_bindings[0].wall_ids == (front_wall_id,)
            and abs(topology.constraint_bindings[0].clearance_m - 0.35) <= 1e-9
            and window.working.history_length == before_binding + 1
        )
        print('A09_ADD_CLEARANCE', binding_ok, flush=True)
        if not binding_ok:
            return False

        set_top_fixture_camera(window)
        before_move = window.working.history_length
        drag(
            window,
            qt_global(window, 3.0, 0.0),
            qt_global(window, 3.0, -0.40),
            app,
        )
        room = window.working.committed_document.room
        topology = window.working.committed_document.wall_topology
        vertices = {} if room is None else {vertex.vertex_id: vertex for vertex in room_vertices(room)}
        front_wall = None if topology is None else next(
            (wall for wall in topology.walls if wall.wall_id == front_wall_id), None
        )
        move_ok = (
            room is not None
            and topology is not None
            and front_wall is not None
            and abs(vertices[front_wall.from_vertex_id].y_m + 0.40) <= 0.04
            and abs(vertices[front_wall.to_vertex_id].y_m + 0.40) <= 0.04
            and topology.constraint_bindings[0].wall_ids == (front_wall_id,)
            and window.working.history_length == before_move + 1
        )
        print('A09_MOUSE_MOVE', move_ok, flush=True)
        if not move_ok:
            return False

        before_split = window.working.history_length
        window.split_wall_action.trigger()
        pump(app, 0.15)
        split_topology = window.working.committed_document.wall_topology
        split_selected = window.selected_wall_id
        split_ok = (
            split_topology is not None
            and len(split_topology.walls) == 5
            and split_selected is not None
            and len(split_topology.constraint_bindings) == 1
            and len(split_topology.constraint_bindings[0].wall_ids) == 2
            and split_topology.constraint_bindings[0].clearance_m == 0.35
            and window.working.history_length == before_split + 1
        )
        print('A09_SPLIT_REFERENCE', split_ok, split_selected, flush=True)
        if not split_ok or split_selected is None:
            return False

        before_opening = window.working.history_length
        window.add_opening_action.trigger()
        pump(app, 0.12)
        opening_topology = window.working.committed_document.wall_topology
        opening_id = None if opening_topology is None or not opening_topology.openings else opening_topology.openings[0].opening_id
        opening_ok = (
            opening_topology is not None
            and len(opening_topology.openings) == 1
            and opening_topology.openings[0].wall_id == split_selected
            and window.working.history_length == before_opening + 1
        )
        print('A09_ADD_OPENING', opening_ok, opening_id, flush=True)
        if not opening_ok or opening_id is None:
            return False

        before_merge = window.working.history_length
        window.merge_wall_action.trigger()
        pump(app, 0.15)
        merged_topology = window.working.committed_document.wall_topology
        merged_id = window.selected_wall_id
        merged_opening = None if merged_topology is None else next(
            (opening for opening in merged_topology.openings if opening.opening_id == opening_id), None
        )
        merge_ok = (
            merged_topology is not None
            and merged_id is not None
            and len(merged_topology.walls) == 4
            and merged_opening is not None
            and merged_opening.wall_id == merged_id
            and merged_topology.constraint_bindings[0].wall_ids == (merged_id,)
            and window.working.history_length == before_merge + 1
        )
        print('A09_MERGE_REFERENCE', merge_ok, merged_id, flush=True)
        if not merge_ok:
            return False

        before_reject = window.working.history_length
        wall_count = len(merged_topology.walls)
        window.delete_wall_action.trigger()
        pump(app, 0.12)
        after_reject = window.working.committed_document.wall_topology
        reject_ok = (
            after_reject is not None
            and len(after_reject.walls) == wall_count
            and window.working.history_length == before_reject
        )
        print('A09_REFERENCED_DELETE_REJECT', reject_ok, flush=True)
        if not reject_ok:
            return False

        # Select the rear wall with the real OS mouse. Its successor is also unreferenced.
        rear_wall = next(
            wall
            for wall in after_reject.walls
            if wall.wall_id != merged_id
            and wall.from_vertex_id.startswith('rear')
        )
        set_top_fixture_camera(window)
        rear_midpoint = wall_midpoint(window, rear_wall.wall_id)
        click(window, qt_global(window, *rear_midpoint), app)
        if window.selected_wall_id != rear_wall.wall_id:
            print('A09_SELECT_DELETE_WALL', False, window.selected_wall_id, flush=True)
            return False

        before_delete = window.working.history_length
        window.delete_wall_action.trigger()
        pump(app, 0.15)
        deleted_topology = window.working.committed_document.wall_topology
        delete_ok = (
            deleted_topology is not None
            and len(deleted_topology.walls) == 3
            and window.working.history_length == before_delete + 1
            and all(opening.opening_id == opening_id for opening in deleted_topology.openings)
            and deleted_topology.constraint_bindings[0].wall_ids == (merged_id,)
        )
        print('A09_DELETE_UNREFERENCED', delete_ok, flush=True)
        if not delete_ok:
            return False

        committed = window.working.committed_document
        undo_ok = window.working.undo()
        redo_ok = window.working.redo()
        redo_exact = window.working.committed_document == committed
        print('A09_UNDO_REDO', undo_ok and redo_ok and redo_exact, flush=True)
        return bool(undo_ok and redo_ok and redo_exact)
    finally:
        window.close()
        pump(app, 0.15)
        window.deleteLater()
        pump(app, 0.15)
        del window
        gc.collect()
        pump(app, 0.10)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run N30b A09 Windows acceptance with real OS mouse input.')
    parser.add_argument('--keep-data', type=Path, default=None)
    args = parser.parse_args()

    app = QApplication.instance() or QApplication([sys.argv[0]])
    if args.keep_data is not None:
        args.keep_data.mkdir(parents=True, exist_ok=True)
        ok = run_a09(app, args.keep_data)
    else:
        with tempfile.TemporaryDirectory(prefix='htdt-a09-') as temp:
            ok = run_a09(app, Path(temp))
    print('A09_RESULT', 'PASS' if ok else 'FAIL', flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
