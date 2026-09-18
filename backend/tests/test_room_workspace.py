from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QDockWidget, QFrame

from htdt.cad_repository import SceneRepository
from htdt.cad_scene import F1_DOCUMENT_ID
from htdt.room_viewport import RoomOverlayState
from htdt.room_workspace import (
    RoomWorkspace,
    RoomWorkspaceController,
    build_room_workspace_mount,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeRoomViewport(QFrame):
    entitySelected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.render_calls: list[tuple[str | None, RoomOverlayState, bool]] = []
        self.focused: list[str] = []
        self.fit_count = 0

    def render_document(
        self,
        document,
        *,
        selected_id: str | None,
        overlays: RoomOverlayState,
        reset_camera: bool = False,
    ) -> None:
        self.render_calls.append((selected_id, overlays, reset_camera))

    def fit_scene(self) -> None:
        self.fit_count += 1

    def focus_entity(self, entity_id: str) -> None:
        self.focused.append(entity_id)


def test_room_controller_reuses_repository_working_document_and_recovery(tmp_path) -> None:
    repository = SceneRepository(tmp_path / "scenes.sqlite3")
    controller = RoomWorkspaceController(repository, F1_DOCUMENT_ID)
    original = repository.latest(F1_DOCUMENT_ID)
    assert original is not None

    added = controller.add_object("speaker")

    assert controller.is_dirty
    assert controller.selected_id == added.entity_id
    assert repository.latest(F1_DOCUMENT_ID).revision_id == original.revision_id
    recovery = repository.recovery(F1_DOCUMENT_ID)
    assert recovery is not None
    assert recovery.document.entity(added.entity_id).name == "スピーカー"

    view_state = repository.view_state(F1_DOCUMENT_ID)
    assert view_state is not None
    assert view_state.selected_id == added.entity_id

    assert controller.save() is True
    saved = repository.latest(F1_DOCUMENT_ID)
    assert saved is not None
    assert saved.revision_id != original.revision_id
    assert saved.document.entity(added.entity_id).speaker_role == "SPK"
    assert repository.recovery(F1_DOCUMENT_ID) is None
    assert not controller.is_dirty


def test_room_controller_deactivation_fails_closed_during_preview(tmp_path) -> None:
    repository = SceneRepository(tmp_path / "scenes.sqlite3")
    controller = RoomWorkspaceController(repository, F1_DOCUMENT_ID)
    entity_id = controller.document.entities[0].entity_id

    controller.working.begin_move(entity_id)
    allowed, reason = controller.before_deactivate()

    assert allowed is False
    assert reason is not None
    assert "プレビュー" in reason

    controller.working.cancel_preview()
    assert controller.before_deactivate() == (True, None)


def test_room_workspace_is_component_composition_and_contextual(tmp_path) -> None:
    app = _app()
    repository = SceneRepository(tmp_path / "scenes.sqlite3")
    workspace = RoomWorkspace(
        repository,
        F1_DOCUMENT_ID,
        viewport_factory=lambda parent: FakeRoomViewport(parent),
    )
    viewport = workspace.viewport

    assert workspace.findChildren(QDockWidget) == []
    assert workspace.current_context == "geometry"
    assert workspace.object_palette.isHidden()

    workspace.set_context("objects")
    assert not workspace.object_palette.isHidden()

    before = len(workspace.controller.document.entities)
    workspace.object_palette.addRequested.emit("seat")
    assert len(workspace.controller.document.entities) == before + 1
    selected_id = workspace.controller.selected_id
    assert selected_id is not None

    workspace.overlay_controls.focus.setChecked(True)
    assert viewport.render_calls[-1][1].focus_selection is True

    workspace.set_context("placement")
    workspace.tools.toolRequested.emit("focus-selection")
    assert viewport.focused[-1] == selected_id

    workspace.set_context("acoustics")
    assert workspace.overlay_controls.acoustics.isChecked()
    assert viewport.render_calls[-1][1].acoustics is True

    workspace.close()
    workspace.deleteLater()
    app.processEvents()


def test_room_workspace_mount_matches_ux110_shell_contract(tmp_path) -> None:
    app = _app()
    repository = SceneRepository(tmp_path / "scenes.sqlite3")
    mount = build_room_workspace_mount(
        repository,
        F1_DOCUMENT_ID,
        viewport_factory=lambda parent: FakeRoomViewport(parent),
    )
    workspace = mount.widget
    assert isinstance(workspace, RoomWorkspace)

    assert mount.on_context_changed is not None
    mount.on_context_changed("placement")
    assert workspace.current_context == "placement"

    entity_id = workspace.controller.document.entities[0].entity_id
    assert mount.on_entity_requested is not None
    mount.on_entity_requested(entity_id)
    assert workspace.controller.selected_id == entity_id

    assert mount.before_deactivate is not None
    assert mount.before_deactivate() == (True, None)

    workspace.close()
    workspace.deleteLater()
    app.processEvents()
