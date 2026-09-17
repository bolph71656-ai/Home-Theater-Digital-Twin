from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QScrollArea

from .cad_repository import SceneRepository
from .cad_scene import F1_DOCUMENT_ID
from .measurement_editor import MeasurementEditorWindow


class MeasurementWorkspaceWindow(MeasurementEditorWindow):
    """N60 product composition with a DPI-safe scrollable measurement dock."""

    def __init__(self, repository: SceneRepository, document_id: str = F1_DOCUMENT_ID) -> None:
        self.measurement_scroll: QScrollArea | None = None
        super().__init__(repository, document_id)

    def _create_measurement_dock(self) -> None:
        super()._create_measurement_dock()
        dock = next(
            (candidate for candidate in self.findChildren(QDockWidget) if candidate.windowTitle() == '実測'),
            None,
        )
        if dock is None:
            return
        panel = dock.widget()
        if panel is None or isinstance(panel, QScrollArea):
            self.measurement_scroll = panel if isinstance(panel, QScrollArea) else None
            return

        # The measurement workspace is a primary N60 surface. Keeping it tabified
        # behind the N50 constraint dock made scene selection able to obscure its
        # controls on Windows, so detach it from that tab stack and keep it directly
        # reachable in the right dock area. The content itself remains scrollable.
        constraint_dock = next(
            (candidate for candidate in self.findChildren(QDockWidget) if candidate.windowTitle() == '制約'),
            None,
        )
        self.removeDockWidget(dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        if constraint_dock is not None:
            self.splitDockWidget(constraint_dock, dock, Qt.Orientation.Vertical)

        # QScrollArea(widgetResizable=True) may otherwise shrink this already-built
        # panel to the viewport height. Preserve the layout's vertical minimum so
        # every control remains reachable at high DPI / short logical screen heights.
        panel.setMinimumHeight(panel.minimumSizeHint().height())
        panel.setParent(None)
        scroll = QScrollArea(dock)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(panel)
        dock.setWidget(scroll)
        self.measurement_scroll = scroll
