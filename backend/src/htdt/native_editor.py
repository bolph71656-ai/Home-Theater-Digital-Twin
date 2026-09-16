from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any, Literal

import numpy as np
import pyvista as pv
from PySide6.QtCore import QEvent, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
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

from .cad_document import EditorViewState, WorkingDocument
from .cad_gizmo import RotationWidget3D, TranslationWidget3D
from .cad_repository import RecoverySnapshot, SceneRepository
from .cad_scene import (
    F1_DOCUMENT_ID,
    Position3,
    Quaternion4,
    SceneEntity,
    domain_pose_to_render_matrix,
    make_f1_scene,
    quaternion_from_euler_deg,
    quaternion_to_euler_deg,
    render_delta_to_domain,
    rotate_orientation_world,
)
from .cad_snap import snap_angle_deg, snap_position_axis

ROLE = int(Qt.ItemDataRole.UserRole)
AXIS_NAMES: tuple[Literal['x', 'y', 'z'], ...] = ('x', 'y', 'z')


def default_data_dir() -> Path:
    base = os.environ.get('LOCALAPPDATA')
    return Path(base) / 'HomeTheaterDigitalTwin' if base else Path.home() / '.home-theater-digital-twin'


class NativeEditorWindow(QMainWindow):
    """N20a native CAD shell: rigid move/rotate, snap, undo, recovery and view state."""

    def __init__(self, repository: SceneRepository, document_id: str = F1_DOCUMENT_ID) -> None:
        super().__init__()
        self.repository = repository
        self.document_id = document_id
        self.working: WorkingDocument | None = None
        self.view_state = EditorViewState()
        self.selected_id: str | None = None
        self.recovery_candidate: RecoverySnapshot | None = None
        self.actors: dict[str, pv.Actor] = {}
        self.actor_ids: dict[int, str] = {}
        self.items: dict[str, QTreeWidgetItem] = {}
        self.gizmo: TranslationWidget3D | RotationWidget3D | None = None
        self.drag_base_position: Position3 | None = None
        self.drag_base_orientation: Quaternion4 | None = None
        self.resize(1440, 900)
        self.setWindowTitle('Home Theater Digital Twin — N20a')

        self.viewport = QtInteractor(self)
        self.setCentralWidget(self.viewport.interactor)
        self.viewport.interactor.installEventFilter(self)
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
        self.state_label = QLabel('—')
        self.aim_label = QLabel('—')
        form.addRow('Type', self.kind_label)
        form.addRow('ID', self.id_label)
        form.addRow('State', self.state_label)

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

        self.orientation_fields: dict[str, QDoubleSpinBox] = {}
        for axis in ('Yaw', 'Pitch', 'Roll'):
            field = QDoubleSpinBox()
            field.setRange(-180.0, 180.0)
            field.setDecimals(2)
            field.setSingleStep(1.0)
            field.setSuffix('°')
            field.setKeyboardTracking(False)
            field.editingFinished.connect(self._numeric_orientation_edited)
            self.orientation_fields[axis] = field
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
        self.delete_action = self._action('Delete', None, self.delete_selected)
        self.delete_action.setShortcut(QKeySequence('Delete'))
        toolbar.addActions((self.save_action, self.undo_action, self.redo_action, self.delete_action))
        toolbar.addSeparator()

        self.transform_group = QActionGroup(self)
        self.transform_group.setExclusive(True)
        self.move_action = self._action('Move', None, self._activate_move_mode)
        self.move_action.setCheckable(True)
        self.move_action.setShortcut(QKeySequence('W'))
        self.rotate_action = self._action('Rotate', None, self._activate_rotate_mode)
        self.rotate_action.setCheckable(True)
        self.rotate_action.setShortcut(QKeySequence('R'))
        self.transform_group.addAction(self.move_action)
        self.transform_group.addAction(self.rotate_action)
        self.move_action.setChecked(True)
        toolbar.addActions((self.move_action, self.rotate_action))

        self.grid_snap_action = self._action('Grid Snap', None, self._grid_snap_toggled)
        self.grid_snap_action.setCheckable(True)
        self.angle_snap_action = self._action('Angle Snap', None, self._angle_snap_toggled)
        self.angle_snap_action.setCheckable(True)
        toolbar.addActions((self.grid_snap_action, self.angle_snap_action))

        self.grid_step_field = QDoubleSpinBox()
        self.grid_step_field.setRange(0.001, 10.0)
        self.grid_step_field.setDecimals(3)
        self.grid_step_field.setSingleStep(0.01)
        self.grid_step_field.setValue(self.view_state.grid_step_m)
        self.grid_step_field.setSuffix(' m grid')
        self.grid_step_field.valueChanged.connect(self._grid_step_changed)
        toolbar.addWidget(self.grid_step_field)

        self.angle_step_field = QDoubleSpinBox()
        self.angle_step_field.setRange(0.1, 180.0)
        self.angle_step_field.setDecimals(1)
        self.angle_step_field.setSingleStep(5.0)
        self.angle_step_field.setValue(self.view_state.angle_step_deg)
        self.angle_step_field.setSuffix('° angle')
        self.angle_step_field.valueChanged.connect(self._angle_step_changed)
        toolbar.addWidget(self.angle_step_field)
        toolbar.addSeparator()

        self.hide_action = self._action('Hidden', None, self._toggle_hidden)
        self.hide_action.setCheckable(True)
        self.lock_action = self._action('Locked', None, self._toggle_locked)
        self.lock_action.setCheckable(True)
        self.show_all_action = self._action('Show All', None, self.show_all)
        toolbar.addActions((self.hide_action, self.lock_action, self.show_all_action))
        toolbar.addSeparator()

        self.recover_action = self._action('Recover Draft', None, self.recover_draft)
        self.discard_recovery_action = self._action('Discard Recovery', None, self.discard_recovery)
        toolbar.addActions((self.recover_action, self.discard_recovery_action))
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

    def _sync_transform_controls(self) -> None:
        with QSignalBlocker(self.move_action):
            self.move_action.setChecked(self.view_state.transform_mode == 'move')
        with QSignalBlocker(self.rotate_action):
            self.rotate_action.setChecked(self.view_state.transform_mode == 'rotate')
        with QSignalBlocker(self.grid_snap_action):
            self.grid_snap_action.setChecked(self.view_state.grid_snap_enabled)
        with QSignalBlocker(self.angle_snap_action):
            self.angle_snap_action.setChecked(self.view_state.angle_snap_enabled)
        with QSignalBlocker(self.grid_step_field):
            self.grid_step_field.setValue(self.view_state.grid_step_m)
        with QSignalBlocker(self.angle_step_field):
            self.angle_step_field.setValue(self.view_state.angle_step_deg)

    def _load_or_seed(self) -> None:
        revision = self.repository.latest(self.document_id)
        if revision is None:
            revision = self.repository.save(make_f1_scene(), parent_revision_id=None).revision
        self.working = WorkingDocument(
            revision.document,
            source_revision_id=revision.revision_id,
            saved_content_hash=revision.content_hash,
        )
        record = self.repository.view_state(self.document_id)
        if record is not None:
            self.view_state = EditorViewState(
                selected_id=record.selected_id,
                hidden_ids=set(record.hidden_ids),
                locked_ids=set(record.locked_ids),
            )
            self.view_state.sanitize(revision.document)
        self._sync_transform_controls()
        self.selected_id = self.view_state.selected_id
        self.recovery_candidate = self.repository.recovery(self.document_id)
        self._rebuild(reset_camera=True)
        if self.recovery_candidate is not None:
            self.statusBar().showMessage(
                f'F1 · revision {revision.revision_id[:8]} · recovery available · choose Recover Draft or Discard Recovery'
            )
        else:
            self.statusBar().showMessage(f'F1 · revision {revision.revision_id[:8]} · clean')

    def _rebuild(self, *, reset_camera: bool = False) -> None:
        if self.working is None:
            return
        selected = self.view_state.selected_id
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
        self._select(selected if selected in self.items else None, cancel_preview=False, persist=False)
        self._update_actions()

    def _add_entity(self, parent: QTreeWidgetItem, entity: SceneEntity) -> None:
        flags: list[str] = []
        if self.view_state.is_hidden(entity.entity_id):
            flags.append('hidden')
        if self.view_state.is_locked(entity.entity_id):
            flags.append('locked')
        suffix = f" · {', '.join(flags)}" if flags else ''
        item = QTreeWidgetItem([f'{entity.name}{suffix}'])
        item.setData(0, ROLE, entity.entity_id)
        parent.addChild(item)
        self.items[entity.entity_id] = item

        if self.view_state.is_hidden(entity.entity_id):
            return
        if entity.kind in {'speaker', 'furniture'}:
            if entity.size_m is None:
                raise ValueError(f'{entity.entity_id} requires size_m for rendering')
            mesh = pv.Cube(
                center=(0.0, 0.0, 0.0),
                x_length=entity.size_m.x_m,
                y_length=entity.size_m.y_m,
                z_length=entity.size_m.z_m,
            )
        else:
            mesh = pv.Sphere(radius=0.08, center=(0.0, 0.0, 0.0))
        mesh.transform(np.asarray(domain_pose_to_render_matrix(entity.position, entity.orientation)), inplace=True)
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

    def _select(
        self,
        entity_id: str | None,
        *,
        cancel_preview: bool = True,
        persist: bool = True,
    ) -> None:
        if cancel_preview and self.working and self.working.has_preview:
            self.cancel_preview()
        self._remove_gizmo()
        if self.working is not None and entity_id is not None:
            try:
                self.working.committed_document.entity(entity_id)
            except KeyError:
                entity_id = None
        self.selected_id = entity_id
        self.view_state.selected_id = entity_id
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            if entity_id in self.items:
                self.items[entity_id].setSelected(True)
        for key, actor in self.actors.items():
            actor.prop.show_edges = key == entity_id
            actor.prop.line_width = 3 if key == entity_id else 1
        self._inspect(entity_id)
        self._create_gizmo(entity_id)
        if persist:
            self._persist_view_state()
        self._update_actions()
        self.viewport.render()

    def _create_gizmo(self, entity_id: str | None) -> None:
        if (
            entity_id is None
            or self.working is None
            or self.recovery_candidate is not None
            or entity_id not in self.actors
            or self.view_state.is_locked(entity_id)
        ):
            return
        entity = self.working.committed_document.entity(entity_id)
        if self.view_state.transform_mode == 'move':
            self.gizmo = TranslationWidget3D(
                self.viewport,
                self.actors[entity_id],
                interact_callback=self._translation_interact,
                release_callback=self._translation_release,
                cancel_callback=self.cancel_preview,
            )
        elif entity.kind in {'speaker', 'furniture'}:
            self.gizmo = RotationWidget3D(
                self.viewport,
                self.actors[entity_id],
                interact_callback=self._rotation_interact,
                release_callback=self._rotation_release,
                cancel_callback=self.cancel_preview,
            )

    def _inspect(self, entity_id: str | None, *, use_preview: bool = False) -> None:
        self.kind_label.setText('—')
        self.id_label.setText('—')
        self.state_label.setText('—')
        self.aim_label.setText('—')
        for field in (*self.position_fields.values(), *self.orientation_fields.values()):
            field.setEnabled(False)
        if entity_id is None or self.working is None:
            return
        document = self.working.document if use_preview else self.working.committed_document
        entity = document.entity(entity_id)
        self.kind_label.setText(entity.kind.replace('_', ' ').title())
        self.id_label.setText(entity.entity_id)
        states = ['Hidden' if self.view_state.is_hidden(entity_id) else 'Visible']
        if self.view_state.is_locked(entity_id):
            states.append('Locked')
        if self.recovery_candidate is not None:
            states.append('Recovery pending')
        self.state_label.setText(' · '.join(states))
        self.aim_label.setText(
            'unknown'
            if entity.kind == 'speaker' and entity.aim_xyz is None
            else ('known' if entity.kind == 'speaker' else '—')
        )
        editable = not self.view_state.is_locked(entity_id) and self.recovery_candidate is None
        position_values = (entity.position.x_m, entity.position.y_m, entity.position.z_m)
        position_blockers = [QSignalBlocker(field) for field in self.position_fields.values()]
        try:
            for field, value in zip(self.position_fields.values(), position_values, strict=True):
                field.setValue(value)
                field.setEnabled(editable)
        finally:
            del position_blockers

        yaw, pitch, roll = quaternion_to_euler_deg(entity.orientation)
        orientation_blockers = [QSignalBlocker(field) for field in self.orientation_fields.values()]
        try:
            for field, value in zip(self.orientation_fields.values(), (yaw, pitch, roll), strict=True):
                field.setValue(value)
                field.setEnabled(editable and entity.kind in {'speaker', 'furniture'})
        finally:
            del orientation_blockers

    def _numeric_position_edited(self) -> None:
        if self.selected_id is None or self.working is None or self.working.has_preview:
            return
        if self.recovery_candidate is not None or self.view_state.is_locked(self.selected_id):
            return
        position = Position3(
            x_m=self.position_fields['X'].value(),
            y_m=self.position_fields['Y'].value(),
            z_m=self.position_fields['Z'].value(),
        )
        if self.working.move_entity(self.selected_id, position):
            self._sync_recovery()
            self._rebuild()
        self._set_dirty_status()

    def _numeric_orientation_edited(self) -> None:
        if self.selected_id is None or self.working is None or self.working.has_preview:
            return
        if self.recovery_candidate is not None or self.view_state.is_locked(self.selected_id):
            return
        entity = self.working.committed_document.entity(self.selected_id)
        if entity.kind not in {'speaker', 'furniture'}:
            return
        orientation = quaternion_from_euler_deg(
            yaw_deg=self.orientation_fields['Yaw'].value(),
            pitch_deg=self.orientation_fields['Pitch'].value(),
            roll_deg=self.orientation_fields['Roll'].value(),
        )
        if self.working.rotate_entity(self.selected_id, orientation):
            self._sync_recovery()
            self._rebuild()
        self._set_dirty_status()

    def _translation_interact(self, matrix: np.ndarray) -> None:
        if self.selected_id is None or self.working is None or self.recovery_candidate is not None:
            return
        if self.view_state.is_locked(self.selected_id) or not isinstance(self.gizmo, TranslationWidget3D):
            return
        if not self.working.has_preview:
            self.drag_base_position = self.working.committed_document.entity(self.selected_id).position
            self.working.begin_move(self.selected_id)
        if self.drag_base_position is None:
            return
        candidate = render_delta_to_domain(tuple(float(value) for value in matrix[:3, 3]), self.drag_base_position)
        axis_index = self.gizmo.active_axis_index
        if self.view_state.grid_snap_enabled and axis_index is not None:
            candidate = snap_position_axis(candidate, AXIS_NAMES[axis_index], self.view_state.grid_step_m)
        display_delta = (
            candidate.x_m - self.drag_base_position.x_m,
            -(candidate.y_m - self.drag_base_position.y_m),
            candidate.z_m - self.drag_base_position.z_m,
        )
        self.gizmo.set_display_delta(display_delta)
        self.working.preview_move(candidate)
        self._inspect(self.selected_id, use_preview=True)

    def _translation_release(self, matrix: np.ndarray) -> None:
        del matrix
        if self.working is None or self.working.preview_kind != 'move':
            return
        self.working.commit_preview()
        self.drag_base_position = None
        self._sync_recovery()
        self._rebuild()
        self._set_dirty_status()

    def _rotation_interact(self, axis_index: int, angle_deg: float) -> None:
        if self.selected_id is None or self.working is None or self.recovery_candidate is not None:
            return
        if self.view_state.is_locked(self.selected_id) or not isinstance(self.gizmo, RotationWidget3D):
            return
        if not self.working.has_preview:
            self.drag_base_orientation = self.working.committed_document.entity(self.selected_id).orientation
            self.working.begin_rotate(self.selected_id)
        if self.drag_base_orientation is None:
            return
        effective_angle = float(angle_deg)
        if self.view_state.angle_snap_enabled:
            effective_angle = snap_angle_deg(effective_angle, self.view_state.angle_step_deg)
        self.gizmo.set_display_angle(effective_angle)
        orientation = rotate_orientation_world(
            self.drag_base_orientation,
            AXIS_NAMES[axis_index],
            effective_angle,
        )
        self.working.preview_rotate(orientation)
        self._inspect(self.selected_id, use_preview=True)

    def _rotation_release(self, axis_index: int, angle_deg: float) -> None:
        del axis_index, angle_deg
        if self.working is None or self.working.preview_kind != 'rotate':
            return
        self.working.commit_preview()
        self.drag_base_orientation = None
        self._sync_recovery()
        self._rebuild()
        self._set_dirty_status()

    def cancel_preview(self) -> None:
        if self.working is None or not self.working.has_preview:
            return
        kind = self.working.preview_kind or 'transform'
        self.working.cancel_preview()
        self.drag_base_position = None
        self.drag_base_orientation = None
        if self.gizmo:
            self.gizmo.cancel()
        self._rebuild()
        self.statusBar().showMessage(f'{kind.title()} cancelled · history unchanged')

    def _activate_move_mode(self, checked: bool = False) -> None:
        del checked
        self._set_transform_mode('move')

    def _activate_rotate_mode(self, checked: bool = False) -> None:
        del checked
        self._set_transform_mode('rotate')

    def _set_transform_mode(self, mode: Literal['move', 'rotate']) -> None:
        if self.working and self.working.has_preview:
            self.cancel_preview()
        if self.view_state.transform_mode == mode:
            return
        self.view_state.transform_mode = mode
        self._sync_transform_controls()
        self._remove_gizmo()
        self._create_gizmo(self.selected_id)
        self.statusBar().showMessage(f'{mode.title()} tool · world axes')
        self._update_actions()
        self.viewport.render()

    def _grid_snap_toggled(self, checked: bool) -> None:
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.grid_snap_enabled = bool(checked)
        self.statusBar().showMessage(
            f"Grid snap {'on' if checked else 'off'} · {self.view_state.grid_step_m:g} m"
        )

    def _angle_snap_toggled(self, checked: bool) -> None:
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.angle_snap_enabled = bool(checked)
        self.statusBar().showMessage(
            f"Angle snap {'on' if checked else 'off'} · {self.view_state.angle_step_deg:g}°"
        )

    def _grid_step_changed(self, value: float) -> None:
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.grid_step_m = float(value)

    def _angle_step_changed(self, value: float) -> None:
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.angle_step_deg = float(value)

    def undo(self) -> None:
        if self.working is None or self.recovery_candidate is not None:
            return
        if self.working.has_preview:
            self.cancel_preview()
            return
        if self.working.undo():
            self._sync_recovery()
            self._rebuild()
            self._set_dirty_status()

    def redo(self) -> None:
        if self.working is None or self.recovery_candidate is not None:
            return
        if self.working.redo():
            self._sync_recovery()
            self._rebuild()
            self._set_dirty_status()

    def delete_selected(self) -> None:
        if self.selected_id is None or self.working is None or self.recovery_candidate is not None:
            return
        if self.view_state.is_locked(self.selected_id):
            self.statusBar().showMessage('Locked object cannot be deleted')
            return
        entity_id = self.selected_id
        if self.working.delete_entity(entity_id):
            self.selected_id = None
            self.view_state.selected_id = None
            self._sync_recovery()
            self._persist_view_state()
            self._rebuild()
            self._set_dirty_status()

    def _toggle_hidden(self, checked: bool) -> None:
        if self.selected_id is None:
            return
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.set_hidden(self.selected_id, checked)
        self._persist_view_state()
        self._rebuild()

    def _toggle_locked(self, checked: bool) -> None:
        if self.selected_id is None:
            return
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.set_locked(self.selected_id, checked)
        self._persist_view_state()
        self._rebuild()

    def show_all(self) -> None:
        if not self.view_state.hidden_ids:
            return
        if self.working and self.working.has_preview:
            self.cancel_preview()
        self.view_state.hidden_ids.clear()
        self._persist_view_state()
        self._rebuild()

    def save(self) -> None:
        if self.working is None or self.recovery_candidate is not None:
            return
        if self.working.has_preview:
            self.statusBar().showMessage('Finish or cancel the active transform before Save')
            return
        try:
            result = self.repository.save(
                self.working.committed_document,
                parent_revision_id=self.working.source_revision_id,
            )
            self.working.mark_saved(result.revision.revision_id, result.revision.content_hash)
        except Exception as exc:
            self.statusBar().showMessage(f'Save failed · draft kept · {exc}')
            QMessageBox.critical(self, 'Save failed', f'{exc}\n\nThe draft and recovery snapshot were kept.')
            return
        verb = 'saved' if result.created else 'unchanged'
        self.statusBar().showMessage(f'Revision {result.revision.revision_id[:8]} · {verb} · clean')
        self._update_actions()

    def recover_draft(self) -> None:
        if self.recovery_candidate is None:
            return
        source_id = self.recovery_candidate.source_revision_id
        source = self.repository.get(source_id) if source_id is not None else None
        if source is None:
            self.statusBar().showMessage('Recovery cannot be opened because its source revision is missing')
            return
        self.working = WorkingDocument(
            self.recovery_candidate.document,
            source_revision_id=source.revision_id,
            saved_content_hash=source.content_hash,
        )
        self.view_state.sanitize(self.working.committed_document)
        self.selected_id = self.view_state.selected_id
        self.recovery_candidate = None
        self._rebuild(reset_camera=True)
        self.statusBar().showMessage(f'Recovered draft from revision {source.revision_id[:8]} · dirty')

    def discard_recovery(self) -> None:
        if self.recovery_candidate is None:
            return
        self.repository.clear_recovery(self.document_id)
        self.recovery_candidate = None
        self._rebuild()
        self.statusBar().showMessage('Recovery draft discarded · formal revision unchanged')

    def _sync_recovery(self) -> None:
        if self.working is None or self.working.has_preview or self.recovery_candidate is not None:
            return
        try:
            if self.working.is_dirty:
                self.repository.save_recovery(
                    self.working.committed_document,
                    source_revision_id=self.working.source_revision_id,
                )
            else:
                self.repository.clear_recovery(self.document_id)
        except Exception as exc:
            self.statusBar().showMessage(f'Recovery snapshot failed · {exc}')

    def _persist_view_state(self) -> None:
        try:
            self.repository.save_view_state(
                self.document_id,
                selected_id=self.view_state.selected_id,
                hidden_ids=self.view_state.hidden_ids,
                locked_ids=self.view_state.locked_ids,
            )
        except Exception as exc:
            self.statusBar().showMessage(f'View state save failed · {exc}')

    def _set_dirty_status(self) -> None:
        if self.working is None:
            return
        self.statusBar().showMessage('dirty' if self.working.is_dirty else 'clean')
        self._update_actions()

    def _update_actions(self) -> None:
        if self.working is None:
            return
        recovery_block = self.recovery_candidate is not None
        selected = self.selected_id is not None
        locked = bool(selected and self.view_state.is_locked(self.selected_id))
        self.save_action.setEnabled(not recovery_block and not self.working.has_preview and self.working.is_dirty)
        self.undo_action.setEnabled(not recovery_block and (self.working.can_undo or self.working.has_preview))
        self.redo_action.setEnabled(not recovery_block and self.working.can_redo and not self.working.has_preview)
        self.delete_action.setEnabled(not recovery_block and selected and not locked and not self.working.has_preview)
        self.show_all_action.setEnabled(bool(self.view_state.hidden_ids))
        self.recover_action.setEnabled(recovery_block and not self.working.is_dirty)
        self.discard_recovery_action.setEnabled(recovery_block and not self.working.is_dirty)
        with QSignalBlocker(self.hide_action):
            self.hide_action.setEnabled(selected)
            self.hide_action.setChecked(bool(selected and self.view_state.is_hidden(self.selected_id)))
        with QSignalBlocker(self.lock_action):
            self.lock_action.setEnabled(selected)
            self.lock_action.setChecked(locked)

    def _remove_gizmo(self) -> None:
        if self.gizmo:
            self.gizmo.remove()
            self.gizmo = None

    def _cancel_before_view_change(self) -> None:
        if self.working and self.working.has_preview:
            self.cancel_preview()

    def _top(self) -> None:
        self._cancel_before_view_change()
        self.viewport.view_xy(negative=True)
        self.viewport.enable_parallel_projection()
        self.viewport.reset_camera()
        self.viewport.render()

    def _front(self) -> None:
        self._cancel_before_view_change()
        self.viewport.view_xz(negative=False)
        self.viewport.enable_parallel_projection()
        self.viewport.reset_camera()
        self.viewport.render()

    def _right(self) -> None:
        self._cancel_before_view_change()
        self.viewport.view_yz(negative=True)
        self.viewport.enable_parallel_projection()
        self.viewport.reset_camera()
        self.viewport.render()

    def _perspective(self) -> None:
        self._cancel_before_view_change()
        self.viewport.disable_parallel_projection()
        self.viewport.view_isometric()
        self.viewport.reset_camera()
        self.viewport.render()

    def _fit(self) -> None:
        self._cancel_before_view_change()
        self.viewport.reset_camera()
        self.viewport.render()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (
            watched is self.viewport.interactor
            and event.type() == QEvent.Type.UngrabMouse
            and self.working is not None
            and self.working.has_preview
        ):
            self.cancel_preview()
        return super().eventFilter(watched, event)

    def event(self, event) -> bool:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and self.working is not None
            and self.working.has_preview
        ):
            self.cancel_preview()
        return super().event(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.working and self.working.has_preview:
            self.working.cancel_preview()
        self._sync_recovery()
        self._persist_view_state()
        self._remove_gizmo()
        self.viewport.close()
        event.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run the HTDT native CAD editor N20a shell')
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
