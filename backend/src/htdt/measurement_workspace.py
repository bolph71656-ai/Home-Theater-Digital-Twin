from __future__ import annotations

from PySide6.QtWidgets import QAbstractScrollArea, QDockWidget, QScrollArea, QSizePolicy

from .cad_repository import SceneRepository
from .cad_scene import F1_DOCUMENT_ID
from .measurement_editor import MeasurementEditorWindow


class MeasurementWorkspaceWindow(MeasurementEditorWindow):
    """N60 product composition with a DPI-safe scrollable measurement dock."""

    def __init__(self, repository: SceneRepository, document_id: str = F1_DOCUMENT_ID) -> None:
        self.measurement_scroll: QScrollArea | None = None
        super().__init__(repository, document_id)
        self._fit_initial_size_to_screen()

    def _fit_initial_size_to_screen(self) -> None:
        """Keep the first product window inside the usable logical screen area."""
        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        margin = 40
        target_width = min(self.width(), max(1, available.width() - margin))
        target_height = min(self.height(), max(1, available.height() - margin))
        self.resize(target_width, target_height)

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

        # Keep the complete measurement form as scrollable content, but do not let
        # that content's large minimum height become a minimum for the top-level
        # QMainWindow. At 200% DPI that would push controls below the usable desktop.
        panel.setMinimumHeight(panel.minimumSizeHint().height())
        panel.setParent(None)
        scroll = QScrollArea(dock)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        scroll.setMinimumSize(0, 0)
        scroll.setWidget(panel)
        dock.setMinimumSize(0, 0)
        dock.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        dock.setWidget(scroll)
        self.measurement_scroll = scroll
