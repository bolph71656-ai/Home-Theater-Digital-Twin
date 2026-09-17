from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from .cad_composition import CadEditorWindow
from .cad_repository import SceneRepository
from .cad_scene import F1_DOCUMENT_ID
from .constraint_editor import ConstraintEditorWindow
from .native_editor import default_data_dir
from .theater_workflow import TheaterWorkflowWindow

# Preserve the public theater-editor alias while the concrete product composition
# advances through N50. Earlier N40 behavior remains inherited unchanged.
TheaterEditorWindow = ConstraintEditorWindow

__all__ = [
    'CadEditorWindow',
    'TheaterEditorWindow',
    'TheaterWorkflowWindow',
    'ConstraintEditorWindow',
    'main',
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='HTDT native CAD editor')
    parser.add_argument('--data-dir', type=Path, default=default_data_dir())
    parser.add_argument('--document-id', default=F1_DOCUMENT_ID)
    args = parser.parse_args(argv)
    app = QApplication([sys.argv[0]])
    repository = SceneRepository(args.data_dir / 'cad-scenes.sqlite3')
    window = ConstraintEditorWindow(repository, args.document_id)
    window.show()
    return int(app.exec())


if __name__ == '__main__':
    raise SystemExit(main())
