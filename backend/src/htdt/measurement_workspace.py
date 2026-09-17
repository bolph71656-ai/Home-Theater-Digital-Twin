from __future__ import annotations

from PySide6.QtCore import QTimer
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
        # QMainWindow resolves dock geometry when the window is first shown. Clamp
        # once more after that layout pass so a high-DPI size hint cannot restore an
        # oversized pre-show geometry.
        QTimer.singleShot(0, self._fit_initial_size_to_screen)

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
            self._unify_right_context_docks(dock)
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
        self._unify_right_context_docks(dock)

    def _unify_right_context_docks(self, measurement_dock: QDockWidget) -> None:
        """Use one CAD-style context stack instead of vertically splitting panels.

        Before N60, the base transform Inspector occupied a separate right-side dock
        row while object details / constraints were tabified below it. Adding the
        measurement workspace to that lower row made the rows' minimum heights add
        together, which could force the whole window below the logical desktop at
        200% Windows scaling. All four surfaces are alternative context views, so a
        single tab group is both the intended CAD interaction and the correct sizing
        boundary.
        """
        titles = ('Inspector', 'オブジェクト詳細', '制約', '実測')
        docks_by_title = {
            candidate.windowTitle(): candidate
            for candidate in self.findChildren(QDockWidget)
            if candidate.windowTitle() in titles
        }
        anchor = docks_by_title.get('Inspector', measurement_dock)
        for title in titles:
            candidate = docks_by_title.get(title)
            if candidate is None:
                continue
            candidate.setMinimumSize(0, 0)
            if candidate is not anchor:
                self.tabifyDockWidget(anchor, candidate)
        measurement_dock.raise_()
