from __future__ import annotations

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from htdt.measurement_workspace import _MeasurementScrollArea


def test_measurement_scroll_does_not_publish_full_content_height() -> None:
    app = QApplication.instance() or QApplication([])

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
