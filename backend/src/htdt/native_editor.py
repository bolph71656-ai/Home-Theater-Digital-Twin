from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pyvista as pv
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from pyvistaqt import QtInteractor

from .cad_document import WorkingDocument
from .cad_gizmo import TranslationWidget3D
from .cad_repository import SceneRepository
from .cad_scene import (
    F1_DOCUMENT_ID,
    Position3,
    SceneEntity,
    domain_to_render,
    make_f1_scene,
    render_delta_to_domain,
)

ROLE = int(Qt.ItemDataRole.UserRole)


def default_data_dir() -> Path:
    base = os.environ.get('LOCALAPPDATA')
    return Path(base) / 'HomeTheaterDigitalTwin' if base else Path.home() / '.home-theater-digital-twin'


class NativeEditorWindow(QMainWindow):
    """N05 vertical slice: one document, shared selection, move, undo and save."""

    def __init__(self, repository: SceneRepository, document_id: str = F1_DOCUMENT_ID) -> None:
        super().__init__()
        self.repository = repository
        self.document_id = document_id
        self.working: WorkingDocument | None = None
        self.selected_id: str | None = None
        self.actors: dict[str, pv.Actor] = {}
        self.actor_ids: dict[int, str] = {}
        self.items: dict[str, QTreeWidgetItem] = {}
        self.gizmo: TranslationWidget3D | None = None
        self.drag_base: Position3 | None = None
        self.resize(1440, 900)
        self.setWindowTitle('Home Theater Digital Twin — N05')

        self.viewport = QtInteractor(self)
        self.setCentralWidget(self.viewport.interactor)
        self.viewport.enable_mesh_picking(
            self._picked,
            show=False,
            show_message=False,
            left_clicking=True,
            use_actor=True,
        )
        self.viewport.add_key_event('Escape', self.cancel_preview)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        left = QDockWidget('Scene', self)
        left.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left)

        inspector = QWidget()
        form = QFormLayout(inspector)
        self.kind_label = QLabel('—')
        self.id_label = QLabel('—')
        self.aim_label = QLabel('—')
        form.addRow('Type', self.kind_label)
        form.addRow('ID', self.id_label)
        self.position_fields: dict[str, QDoubleSpinBox] = {}
        for axis in ('X', 'Y', 'Z'):
            field = QDoubleSpinBox()
            field.setRange(-1000.0, 1000.0)
            field.setDecimals(4)
            field.setSingleStep(0.01)
            field.setSuffix(' m')
            field.setKeyboardTracking(False)
            field.editingFinished.connect(self._numeric_position_edited)
            self.position_fields[axis] = field
            form.addRow(axis, field)
        form.addRow('Aim', self.aim_label)
        right = QDockWidget('Inspector', self)
        right.setWidget(inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right)

        toolbar = QToolBar('Editor', self)
        self.addToolBar(toolbar)
        self.save_action = self._action('Save', QKeySequence.StandardKey.Save, self.save)
        self.undo_action = self._action('Undo', QKeySequence.StandardKey.Undo, self.undo)
        self.redo_action = self._action('Redo', QKeySequence.StandardKey.Redo, self.redo)
        toolbar.addActions((self.save_action, self.undo_action, self.redo_action))
        toolbar.addSeparator()
        for label, callback in (
            ('Top', self._top),
            ('Front', self._front),
            ('Right', self._right),
            ('Perspective', self._perspective),
            ('Fit', self._fit),
        ):
            toolbar.addAction(self._action(label, None, callback))

        self._load_or_seed()

    def _action(self, label: str, shortcut: QKeySequence.StandardKey | None, callback) -> QAction:
        action = QAction(label, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        return action

    def _load_or_seed(self) -> None:
        revision = self.repository.latest(self.document_id)
        if revision is None:
            revision = self.repository.save(make_f1_scene(), parent_revision_id=None).revision
        self.working = WorkingDocument(revision.document, source_revision_id=revision.revision_id)
        self.working.mark_saved(revision.revision_id, revision.content_hash)
        self._rebuild(reset_camera=True)
        self.statusBar().showMessage(f'F1 · revision {revision.revision_id[:8]} · clean')

    def _rebuild(self, *, reset_camera: bool = False) -> None:
        if self.working is None:
            return
        selected = self.selected_id
        self._remove_gizmo()
        self.viewport.clear()
        self.viewport.add_axes()
        self.viewport.show_grid()
        self.tree.clear()
        self.actors.clear()
        self.actor_ids.clear()
        self.items.clear()
        document = self.working.committed_document

        room_item = QTreeWidgetItem(['Room · F1 6×4×2.4 m'])
        self.tree.addTopLevelItem(room_item)
        room_actor = self.viewport.add_mesh(
            pv.Box(bounds=(0.0, document.room.width_m, -document.room.depth_m, 0.0, 0.0, document.room.height_m)),
            style='wireframe',
            line_width=2,
            pickable=False,
        )
        room_actor.prop.opacity = 0.45

        groups: dict[str, QTreeWidgetItem] = {}
        for key, label in (
            ('speaker', 'Speakers'),
            ('measurement_point', 'Listening / Measurement'),
            ('furniture', 'Furniture'),
        ):
            groups[key] = QTreeWidgetItem([label])
            self.tree.addTopLevelItem(groups[key])
        for entity in document.entities:
            self._add_entity(groups[entity.kind], entity)
        self.tree.expandAll()
        if reset_camera:
            self._perspective()
        self._select(selected if selected in self.items else None, cancel_preview=False)
        self._update_actions()

    def _add_entity(self, parent: QTreeWidgetItem, entity: SceneEntity) -> None:
        item = QTreeWidgetItem([entity.name])
        item.setData(0, ROLE, entity.entity_id)
        parent.addChild(item)
        self.items[entity.entity_id] = item
        center = domain_to_render(entity.position)
        if entity.kind in {'speaker', 'furniture'}:
            if entity.size_m is None:
                raise ValueError(f'{entity.entity_id} requires size_m for rendering')
            mesh = pv.Cube(
                center=center,
                x_length=entity.size_m.x_m,
                y_length=entity.size_m.y_m,
                z_length=entity.size_m.z_m,
            )
        else:
            mesh = pv.Sphere(radius=0.08, center=center)
        actor = self.viewport.add_mesh(mesh, name=f'entity:{entity.entity_id}', pickable=True)
        self.actors[entity.entity_id] = actor
        self.actor_ids[id(actor)] = entity.entity_id

    def _picked(self, actor: Any) -> None:
        entity_id = self.actor_ids.get(id(actor))
        if entity_id:
            self._select(entity_id)

    def _tree_selected(self) -> None:
        selected = self.tree.selectedItems()
        entity_id = selected[0].data(0, ROLE) if selected else None
        if isinstance(entity_id, str):
            self._select(entity_id)

    def _select(self, entity_id: str | None, *, cancel_preview: bool = True) -> None:
        if cancel_preview and self.working and self.working.has_preview:
            self.cancel_preview()
        self._remove_gizmo()
        self.selected_id = entity_id
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            if entity_id in self.items:
                self.items[entity_id].setSelected(True)
        for key, actor in self.actors.items():
            actor.prop.show_edges = key == entity_id
            actor.prop.line_width = 3 if key == entity_id else 1
        self._inspect(entity_id)
        if entity_id and self.working:
            entity = self.working.committed_document.entity(entity_id)
            if entity.kind == 'speaker':
                self.gizmo = TranslationWidget3D(
                    self.viewport,
                    self.actors[entity_id],
                    interact_callback=self._gizmo_interact,
                    release_callback=self._gizmo_release,
                )
        self.viewport.render()

    def _inspect(self, entity_id: str | None, *, use_preview: bool = False) -> None:
        self.kind_label.setText('—')
        self.id_label.setText('—')
        self.aim_label.setText('—')
        for field in self.position_fields.values():
            field.setEnabled(False)
        if entity_id is None or self.working is None:
            return
        document = self.working.document if use_preview else self.working.committed_document
        entity = document.entity(entity_id)
        self.kind_label.setText(entity.kind.replace('_', ' ').title())
        self.id_label.setText(entity.entity_id)
        self.aim_label.setText(
            'unknown'
            if entity.kind == 'speaker' and entity.aim_xyz is None
            else ('known' if entity.kind == 'speaker' else '—')
        )
        values = (entity.position.x_m, entity.position.y_m, entity.position.z_m)
        blockers = [QSignalBlocker(field) for field in self.position_fields.values()]
        try:
            for field, value in zip(self.position_fields.values(), values, strict=True):
                field.setValue(value)
                field.setEnabled(True)
        finally:
            del blockers

    def _numeric_position_edited(self) -> None:
        if self.selected_id is None or self.working is None or self.working.has_preview:
            return
        position = Position3(
            x_m=self.position_fields['X'].value(),
            y_m=self.position_fields['Y'].value(),
            z_m=self.position_fields['Z'].value(),
        )
        if self.working.move_entity(self.selected_id, position):
            self._rebuild()
        self._set_dirty_status()

    def _gizmo_interact(self, matrix: np.ndarray) -> None:
        if self.selected_id is None or self.working is None:
            return
        if not self.working.has_preview:
            self.drag_base = self.working.committed_document.entity(self.selected_id).position
            self.working.begin_move(self.selected_id)
        if self.drag_base is None:
            return
        self.working.preview_move(render_delta_to_domain(tuple(matrix[:3, 3]), self.drag_base))
        self._inspect(self.selected_id, use_preview=True)

    def _gizmo_release(self, matrix: np.ndarray) -> None:
        del matrix
        if self.working is None or not self.working.has_preview:
            return
        self.working.commit_preview()
        self.drag_base = None
        self._rebuild()
        self._set_dirty_status()

    def cancel_preview(self) -> None:
        if self.working is None or not self.working.has_preview:
            return
        self.working.cancel_preview()
        self.drag_base = None
        if self.gizmo:
            self.gizmo.cancel()
        self._rebuild()
        self.statusBar().showMessage('Move cancelled · history unchanged')

    def undo(self) -> None:
        if self.working is None:
            return
        if self.working.has_preview:
            self.cancel_preview()
            return
        if self.working.undo():
            self._rebuild()
            self._set_dirty_status()

    def redo(self) -> None:
        if self.working and self.working.redo():
            self._rebuild()
            self._set_dirty_status()

    def save(self) -> None:
        if self.working is None:
            return
        if self.working.has_preview:
            self.statusBar().showMessage('Finish or cancel the active move before Save')
            return
        try:
            result = self.repository.save(
                self.working.committed_document,
                parent_revision_id=self.working.source_revision_id,
            )
            self.working.mark_saved(result.revision.revision_id, result.revision.content_hash)
        except Exception as exc:
            QMessageBox.critical(self, 'Save failed', str(exc))
            return
        verb = 'saved' if result.created else 'unchanged'
        self.statusBar().showMessage(f'Revision {result.revision.revision_id[:8]} · {verb} · clean')
        self._update_actions()

    def _set_dirty_status(self) -> None:
        if self.working is None:
            return
        self.statusBar().showMessage('dirty' if self.working.is_dirty else 'clean')
        self._update_actions()

    def _update_actions(self) -> None:
        if self.working is None:
            return
        self.save_action.setEnabled(not self.working.has_preview and self.working.is_dirty)
        self.undo_action.setEnabled(self.working.can_undo or self.working.has_preview)
        self.redo_action.setEnabled(self.working.can_redo and not self.working.has_preview)

    def _remove_gizmo(self) -> None:
        if self.gizmo:
            self.gizmo.remove()
            self.gizmo = None

    def _top(self) -> None:
        self.viewport.view_xy(negative=True)
        self.viewport.enable_parallel_projection()
        self._fit()

    def _front(self) -> None:
        self.viewport.view_xz(negative=False)
        self.viewport.enable_parallel_projection()
        self._fit()

    def _right(self) -> None:
        self.viewport.view_yz(negative=True)
        self.viewport.enable_parallel_projection()
        self._fit()

    def _perspective(self) -> None:
        self.viewport.disable_parallel_projection()
        self.viewport.view_isometric()
        self._fit()

    def _fit(self) -> None:
        self.viewport.reset_camera()
        self.viewport.render()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.working and self.working.has_preview:
            self.working.cancel_preview()
        self._remove_gizmo()
        self.viewport.close()
        event.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run the HTDT native CAD editor N05 slice')
    parser.add_argument('--data-dir', type=Path, default=default_data_dir())
    parser.add_argument('--document-id', default=F1_DOCUMENT_ID)
    args = parser.parse_args(argv)
    app = QApplication([sys.argv[0]])
    repository = SceneRepository(args.data_dir / 'cad-scenes.sqlite3')
    window = NativeEditorWindow(repository, args.document_id)
    window.show()
    return int(app.exec())


if __name__ == '__main__':
    raise SystemExit(main())
