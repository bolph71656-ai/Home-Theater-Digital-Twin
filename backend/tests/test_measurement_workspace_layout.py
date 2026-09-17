from __future__ import annotations

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QVBoxLayout, QWidget

from htdt.measurement_workspace import MeasurementWorkspaceWindow, _MeasurementScrollArea


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_measurement_scroll_does_not_publish_full_content_height() -> None:
    app = _app()

    content = QWidget()
    layout = QVBoxLayout(content)
    for index in range(48):
        layout.addWidget(QLabel(f'row {index}'))

    scroll = _MeasurementScrollArea(content)
    scroll.resize(420, 320)
    scroll.show()
    app.processEvents()

    assert content.height() > scroll.viewport().height()
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.minimumSizeHint().height() <= 160
    assert scroll.sizeHint().height() == 560

    scroll.close()
    scroll.deleteLater()
    content.deleteLater()
    app.processEvents()


def test_right_context_docks_are_rebuilt_as_one_tab_stack() -> None:
    app = _app()
    window = QMainWindow()
    window.resize(900, 600)

    titles = ('Inspector', 'オブジェクト詳細', '制約', '実測')
    docks: dict[str, QDockWidget] = {}
    for title in titles:
        dock = QDockWidget(title, window)
        dock.setWidget(QLabel(title))
        window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        docks[title] = dock

    # Reproduce the inherited pre-N60 topology: Inspector above a lower tab group.
    window.splitDockWidget(docks['Inspector'], docks['オブジェクト詳細'], Qt.Orientation.Vertical)
    window.tabifyDockWidget(docks['オブジェクト詳細'], docks['制約'])
    window.tabifyDockWidget(docks['制約'], docks['実測'])
    window.show()
    app.processEvents()

    MeasurementWorkspaceWindow._unify_right_context_docks(window, docks['実測'])
    app.processEvents()

    tabbed = set(window.tabifiedDockWidgets(docks['Inspector']))
    assert tabbed == {docks['オブジェクト詳細'], docks['制約'], docks['実測']}
    assert all(
        window.dockWidgetArea(dock) == Qt.DockWidgetArea.RightDockWidgetArea
        for dock in docks.values()
    )

    window.close()
    window.deleteLater()
    app.processEvents()
