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
from .room_editor import RoomEditorWindow
from .runtime_instance import SingleInstanceGuard
from .theater_workflow import TheaterWorkflowWindow
from .workflow_shell import (
    WorkflowShellWindow,
    WorkspaceId,
    WorkspaceMount,
    build_canonical_workspace_registrations,
    make_overview_mount,
)

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
    'WorkflowShellWindow',
    'build_workflow_shell',
    'main',
]


def build_workflow_shell(repository: SceneRepository, document_id: str) -> WorkflowShellWindow:
    """Compose the shell from replaceable workspace factories.

    Room/measurement/optimization currently bridge the existing product windows.
    Their factories are intentionally isolated here so future workspace rewrites can
    replace one destination at a time without changing shell navigation or domain
    authority.
    """

    factories = {
        WorkspaceId.OVERVIEW: make_overview_mount,
        WorkspaceId.ROOM: lambda: WorkspaceMount.from_widget(
            RoomEditorWindow(repository, document_id)
        ),
        WorkspaceId.MEASUREMENT: lambda: WorkspaceMount.from_widget(
            MeasurementWorkspaceWindow(repository, document_id)
        ),
        WorkspaceId.OPTIMIZATION: lambda: WorkspaceMount.from_widget(
            OptimizationWorkspaceWindow(repository, document_id)
        ),
    }
    return WorkflowShellWindow(build_canonical_workspace_registrations(factories))


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

    guard = SingleInstanceGuard(args.data_dir)
    if not guard.acquire():
        print(
            'HTDT data directory is already in use by another process: '
            f'{args.data_dir}',
            file=sys.stderr,
        )
        return 2

    try:
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
                f'extended={result.extended_search_id} '
                f'adaptive-extended={result.adaptive_extended_plan_id}'
            )
            print('synthetic demo is development-only and does not unlock owned-room recommendation')
            return 0

        app = QApplication([sys.argv[0]])
        repository = SceneRepository(args.data_dir / 'cad-scenes.sqlite3')
        window = build_workflow_shell(repository, args.document_id)
        window.show()
        return int(app.exec())
    finally:
        guard.release()


if __name__ == '__main__':
    raise SystemExit(main())
