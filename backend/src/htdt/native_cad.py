from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .cad_composition import CadEditorWindow
from .cad_repository import SceneRepository
from .cad_scene import F1_DOCUMENT_ID
from .cad_synthetic_demo import seed_synthetic_optimization_demo
from .constraint_editor import ConstraintEditorWindow
from .measurement_editor import MeasurementEditorWindow
from .measurement_workspace import MeasurementWorkspaceWindow
from .native_backup import create_backup, restore_backup
from .native_editor import default_data_dir
from .optimization_workspace import OptimizationWorkspaceWindow
from .prediction_workspace import PredictionWorkspaceWindow
from .theater_workflow import TheaterWorkflowWindow

# Preserve the public theater-editor alias while the concrete product composition
# advances through N80. N40-N70 behavior remains inherited unchanged.
TheaterEditorWindow = OptimizationWorkspaceWindow

__all__ = [
    'CadEditorWindow',
    'TheaterEditorWindow',
    'TheaterWorkflowWindow',
    'ConstraintEditorWindow',
    'MeasurementEditorWindow',
    'MeasurementWorkspaceWindow',
    'PredictionWorkspaceWindow',
    'OptimizationWorkspaceWindow',
    'main',
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='HTDT native CAD editor')
    parser.add_argument('--data-dir', type=Path, default=default_data_dir())
    parser.add_argument('--document-id', default=F1_DOCUMENT_ID)
    maintenance = parser.add_mutually_exclusive_group()
    maintenance.add_argument(
        '--backup',
        type=Path,
        metavar='ARCHIVE',
        help='create a validated .htdt-backup archive and exit',
    )
    maintenance.add_argument(
        '--restore',
        type=Path,
        metavar='ARCHIVE',
        help='restore a validated .htdt-backup archive and exit',
    )
    maintenance.add_argument(
        '--seed-synthetic-demo',
        action='store_true',
        help='seed an explicitly synthetic O10-O80 development demo and exit',
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args(argv)

    if args.backup is not None:
        manifest = create_backup(args.data_dir, args.backup)
        print(
            f'backup created: {args.backup} '
            f'(schema={manifest.schema_version}, files={len(manifest.files)})'
        )
        return 0
    if args.restore is not None:
        manifest, pre_restore = restore_backup(args.data_dir, args.restore)
        suffix = '' if pre_restore is None else f' · pre-restore backup: {pre_restore}'
        print(
            f'backup restored: {args.restore} '
            f'(schema={manifest.schema_version}, files={len(manifest.files)}){suffix}'
        )
        return 0
    if args.seed_synthetic_demo:
        repository = SceneRepository(args.data_dir / 'cad-scenes.sqlite3')
        result = seed_synthetic_optimization_demo(repository)
        print(
            'synthetic demo seeded: '
            f'document={result.document_id} '
            f'search={result.search_spec_id} '
            f'validation={result.validation_id} '
            f'adaptive={result.adaptive_plan_id} '
            f'extended={result.extended_search_id}'
        )
        print('synthetic demo is development-only and does not unlock owned-room recommendation')
        return 0

    app = QApplication([sys.argv[0]])
    repository = SceneRepository(args.data_dir / 'cad-scenes.sqlite3')
    window = OptimizationWorkspaceWindow(repository, args.document_id)
    window.show()
    return int(app.exec())


if __name__ == '__main__':
    raise SystemExit(main())
