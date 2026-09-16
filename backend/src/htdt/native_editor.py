from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

import pyvista as pv
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDockWidget, QFormLayout, QLabel, QMainWindow, QToolBar, QTreeWidget, QTreeWidgetItem, QWidget
from pyvistaqt import QtInteractor

from .database import Store
from .models import ContextCreate
from .spatial_editor import ContextDraft

ROLE = int(Qt.ItemDataRole.UserRole)


def default_data_dir() -> Path:
    base = os.environ.get('LOCALAPPDATA')
    return Path(base) / 'HomeTheaterDigitalTwin' if base else Path.home() / '.home-theater-digital-twin'


class NativeEditorWindow(QMainWindow):
    """N10 shell: native viewport, scene tree, inspector and shared selection."""

    def __init__(self, store: Store) -> None:
        super().__init__()
        self.store = store
        self.context: dict[str, Any] | None = None
        self.draft: ContextDraft | None = None
        self.selected_id: str | None = None
        self.actors: dict[str, Any] = {}
        self.actor_ids: dict[int, str] = {}
        self.items: dict[str, QTreeWidgetItem] = {}
        self.resize(1440, 900)
        self.setWindowTitle('Home Theater Digital Twin — Native Editor')

        self.viewport = QtInteractor(self)
        self.setCentralWidget(self.viewport.interactor)
        self.viewport.enable_mesh_picking(self._picked, show=False, show_message=False, left_clicking=True, use_actor=True)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        left = QDockWidget('Scene', self)
        left.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left)

        inspector = QWidget()
        form = QFormLayout(inspector)
        self.fields = {key: QLabel('—') for key in ('type', 'id', 'name', 'position', 'details')}
        self.fields['details'].setWordWrap(True)
        for caption, key in [('Type', 'type'), ('ID', 'id'), ('Name / role', 'name'), ('Position', 'position'), ('Details', 'details')]:
            form.addRow(caption, self.fields[key])
        right = QDockWidget('Inspector', self)
        right.setWidget(inspector)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right)

        toolbar = QToolBar('View', self)
        self.addToolBar(toolbar)
        for label, callback in [('Top', self._top), ('Front', self._front), ('Right', self._right), ('Perspective', self._perspective), ('Fit', self._fit)]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
        self.statusBar().showMessage('No Context loaded')

    def load(self, project_id: str | None = None, context_id: str | None = None) -> bool:
        projects = self.store.list_projects()
        project = self.store.get_project(project_id) if project_id else (projects[0] if projects else None)
        if project is None:
            self.statusBar().showMessage('No HTDT project found')
            return False
        contexts = self.store.list_contexts(project['id'])
        context = self.store.get_context(project['id'], context_id) if context_id else (contexts[0] if contexts else None)
        if context is None:
            self.statusBar().showMessage('No Context revision found')
            return False
        ContextCreate.model_validate(context['payload'])
        self.context = context
        self.draft = ContextDraft(project['id'], context)
        self.setWindowTitle(f"Home Theater Digital Twin — {project['name']} — Context r{context['revision_number']}")
        self._rebuild()
        self.statusBar().showMessage(f"Context r{context['revision_number']} · {context['id']}")
        return True

    def _rebuild(self) -> None:
        payload = self.draft.payload if self.draft else None
        if payload is None:
            return
        self.viewport.clear()
        self.viewport.add_axes()
        self.viewport.show_grid()
        self.tree.clear()
        self.actors.clear(); self.actor_ids.clear(); self.items.clear()

        room_item = self._item(self.tree.invisibleRootItem(), 'Room', 'room')
        room_actor = self.viewport.add_mesh(self._room_mesh(payload['room']), line_width=2, name='room', pickable=True)
        self._actor('room', room_actor)

        speakers = QTreeWidgetItem(['Speakers']); self.tree.addTopLevelItem(speakers)
        for speaker in payload.get('speakers', []):
            entity_id = str(speaker['speaker_id'])
            self._item(speakers, f"{speaker['role']} · {entity_id}", entity_id)
            position = speaker.get('position')
            if position:
                mesh = pv.Cube(center=(position['x_m'], position['y_m'], position['z_m']), x_length=.24, y_length=.20, z_length=.34)
                self._actor(entity_id, self.viewport.add_mesh(mesh, name=f'speaker:{entity_id}', pickable=True))

        group = QTreeWidgetItem(['Listening / Measurement']); self.tree.addTopLevelItem(group)
        point = payload['measurement_point']; entity_id = str(point['point_id'])
        self._item(group, f"{point['label']} · {entity_id}", entity_id)
        p = point['position']
        self._actor(entity_id, self.viewport.add_mesh(pv.Sphere(radius=.08, center=(p['x_m'], p['y_m'], p['z_m'])), name=f'point:{entity_id}', pickable=True))
        self.tree.expandAll(); self._perspective()

    def _item(self, parent: QTreeWidgetItem, text: str, entity_id: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text]); item.setData(0, ROLE, entity_id); parent.addChild(item); self.items[entity_id] = item; return item

    def _actor(self, entity_id: str, actor: Any) -> None:
        self.actors[entity_id] = actor; self.actor_ids[id(actor)] = entity_id

    @staticmethod
    def _room_mesh(room: dict[str, Any]) -> pv.PolyData:
        if room.get('geometry_kind') == 'polygon_prism':
            footprint = [(float(v['x_m']), float(v['y_m'])) for v in room.get('footprint_vertices') or []]
        else:
            w, d = float(room['width_m']), float(room['depth_m']); footprint = [(0, 0), (w, 0), (w, d), (0, d)]
        h, n = float(room['height_m']), len(footprint)
        if n < 3: raise ValueError('room footprint requires at least three vertices')
        mesh = pv.PolyData([(x, y, 0) for x, y in footprint] + [(x, y, h) for x, y in footprint])
        lines: list[int] = []
        for i in range(n):
            j = (i + 1) % n; lines += [2, i, j, 2, n + i, n + j, 2, i, n + i]
        mesh.lines = lines
        return mesh

    def _picked(self, actor: Any) -> None:
        entity_id = self.actor_ids.get(id(actor))
        if entity_id: self._select(entity_id)

    def _tree_selected(self) -> None:
        selected = self.tree.selectedItems()
        entity_id = selected[0].data(0, ROLE) if selected else None
        if isinstance(entity_id, str): self._select(entity_id)

    def _select(self, entity_id: str | None) -> None:
        self.selected_id = entity_id
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            if entity_id in self.items: self.items[entity_id].setSelected(True)
        for key, actor in self.actors.items():
            actor.prop.line_width = 4 if key == entity_id else (2 if key == 'room' else 1)
            if key != 'room': actor.prop.show_edges = key == entity_id
        self._inspect(entity_id); self.viewport.render()

    def _inspect(self, entity_id: str | None) -> None:
        for value in self.fields.values(): value.setText('—')
        if entity_id is None or self.draft is None: return
        payload = self.draft.payload; self.fields['id'].setText(entity_id)
        if entity_id == 'room':
            room = payload['room']; self.fields['type'].setText('Room'); self.fields['name'].setText(room['geometry_kind']); self.fields['details'].setText(f"{room['width_m']:.3f} × {room['depth_m']:.3f} × {room['height_m']:.3f} m"); return
        point = payload['measurement_point']
        if point['point_id'] == entity_id:
            self.fields['type'].setText('Measurement point'); self.fields['name'].setText(point['label']); self.fields['position'].setText(self._position(point['position'])); return
        for speaker in payload.get('speakers', []):
            if speaker['speaker_id'] == entity_id:
                self.fields['type'].setText('Speaker'); self.fields['name'].setText(speaker['role']); self.fields['position'].setText('Unknown' if speaker.get('position') is None else self._position(speaker['position'])); self.fields['details'].setText('Aim: unknown' if speaker.get('aim_xyz') is None else f"Aim: {tuple(speaker['aim_xyz'])}"); return

    @staticmethod
    def _position(p: dict[str, Any]) -> str: return f"X {p['x_m']:.3f}  Y {p['y_m']:.3f}  Z {p['z_m']:.3f} m"
    def _top(self) -> None: self.viewport.view_xy(); self.viewport.enable_parallel_projection(); self._fit()
    def _front(self) -> None: self.viewport.view_xz(); self.viewport.enable_parallel_projection(); self._fit()
    def _right(self) -> None: self.viewport.view_yz(); self.viewport.enable_parallel_projection(); self._fit()
    def _perspective(self) -> None: self.viewport.disable_parallel_projection(); self.viewport.view_isometric(); self._fit()
    def _fit(self) -> None: self.viewport.reset_camera(); self.viewport.render()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run the HTDT native 3D editor')
    parser.add_argument('--data-dir', type=Path); parser.add_argument('--project-id'); parser.add_argument('--context-id')
    args = parser.parse_args(argv)
    if args.context_id and not args.project_id: parser.error('--context-id requires --project-id')
    app = QApplication([sys.argv[0]])
    window = NativeEditorWindow(Store(args.data_dir or default_data_dir()))
    window.load(args.project_id, args.context_id); window.show()
    return int(app.exec())


if __name__ == '__main__': raise SystemExit(main())
