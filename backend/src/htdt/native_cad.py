from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .cad_composition import CadEditorWindow
from .cad_measurement_repository import CadMeasurementRepository
from .cad_model_validation_repository import CadModelValidationRepository
from .cad_objective_repository import CadObjectiveRepository
from .cad_prediction_repository import CadPredictionRepository
from .cad_repository import SceneRepository
from .cad_roomsim_repository import CadRoomSimRepository
from .cad_scene import F1_DOCUMENT_ID
from .cad_search_repository import CadSearchRepository
from .cad_synthetic_demo import seed_synthetic_optimization_demo
from .command_palette import CommandPaletteController
from .command_registry import CommandContext, CommandRegistry, register_default_commands
from .constraint_editor import ConstraintEditorWindow
from .measurement_editor import MeasurementEditorWindow
from .measurement_workspace import MeasurementWorkspaceWindow
from .native_backup import create_backup, restore_backup
from .native_command_adapter import (
    bind_active_editor_commands,
    bind_native_workspace_commands,
    unbind_active_editor_commands,
)
from .native_editor import default_data_dir
from .optimization_workspace import OptimizationWorkspaceWindow
from .overview_readiness import OverviewReadinessService
from .overview_workspace import OverviewWorkspace
from .prediction_workspace import PredictionWorkspaceWindow
from .runtime_instance import SingleInstanceGuard
from .theater_workflow import TheaterWorkflowWindow
from .ui_theme import apply_dark_theme
from .workflow_legacy_bridge import (
    legacy_editor_deactivation_guard,
    raise_legacy_context,
    refresh_legacy_editor_revision,
    select_legacy_entity,
)
from .workflow_navigation import WorkspaceDeepLink, WorkspaceId
from .workflow_shell import (
    WorkflowShellWindow,
    WorkspaceMount,
    build_canonical_workspace_registrations,
)

# Preserve the public theater-editor alias while the concrete product composition
# advances through N80. N40-N70 behavior remains inherited unchanged.
TheaterEditorWindow = OptimizationWorkspaceWindow

__all__ = [
    "CadEditorWindow",
    "TheaterEditorWindow",
    "TheaterWorkflowWindow",
    "ConstraintEditorWindow",
    "MeasurementEditorWindow",
    "MeasurementWorkspaceWindow",
    "PredictionWorkspaceWindow",
    "OptimizationWorkspaceWindow",
    "WorkflowShellWindow",
    "build_workflow_shell",
    "main",
]


def _build_overview_service(repository: SceneRepository) -> OverviewReadinessService:
    """Compose existing read authorities once; Overview itself remains read-only."""

    measurement_repository = CadMeasurementRepository(repository)
    prediction_repository = CadPredictionRepository(repository)
    search_repository = CadSearchRepository(repository)
    roomsim_repository = CadRoomSimRepository(repository, search_repository)
    objective_repository = CadObjectiveRepository(repository, search_repository)
    validation_repository = CadModelValidationRepository(
        search_repository,
        roomsim_repository,
        measurement_repository,
        objective_repository,
    )
    return OverviewReadinessService(
        repository,
        measurement_repository,
        prediction_repository,
        search_repository,
        validation_repository,
    )


def build_workflow_shell(repository: SceneRepository, document_id: str) -> WorkflowShellWindow:
    """Compose the UX110 shell without moving domain authority into the shell.

    Existing QMainWindow workspaces are a temporary bridge. Navigation refuses to
    leave a workspace with a live draft/preview/background worker, and a clean
    workspace reloads the latest SceneRevision when it becomes active. UX120-UX140
    can later replace each bridge with a shared-document workspace view.
    """

    registry = CommandRegistry()
    register_default_commands(registry)
    overview_service = _build_overview_service(repository)
    shell_holder: dict[str, WorkflowShellWindow] = {}

    def navigate_target(target: WorkspaceDeepLink) -> bool:
        shell = shell_holder.get("shell")
        return False if shell is None else shell.handle_deep_link(target)

    def make_overview() -> WorkspaceMount:
        page = OverviewWorkspace(
            overview_service,
            document_id,
            navigate=navigate_target,
        )

        def activate() -> None:
            unbind_active_editor_commands(registry)
            page.refresh()

        return WorkspaceMount.from_widget(page, on_activate=activate)

    def make_legacy(
        workspace_id: WorkspaceId,
        factory,
    ) -> WorkspaceMount:
        window = factory()
        bind_native_workspace_commands(registry, window, workspace_id)

        def activate() -> None:
            refresh_legacy_editor_revision(window)
            bind_active_editor_commands(registry, window)

        return WorkspaceMount.from_widget(
            window,
            on_activate=activate,
            before_deactivate=lambda: legacy_editor_deactivation_guard(window),
            on_context_changed=lambda context_id: raise_legacy_context(
                window,
                workspace_id,
                context_id,
            ),
            on_entity_requested=lambda entity_id: select_legacy_entity(window, entity_id),
        )

    factories = {
        WorkspaceId.OVERVIEW: make_overview,
        # PredictionWorkspaceWindow retains the complete N20-N70 Room/placement/
        # prediction authority needed by the current Room bridge.
        WorkspaceId.ROOM: lambda: make_legacy(
            WorkspaceId.ROOM,
            lambda: PredictionWorkspaceWindow(repository, document_id),
        ),
        WorkspaceId.MEASUREMENT: lambda: make_legacy(
            WorkspaceId.MEASUREMENT,
            lambda: MeasurementWorkspaceWindow(repository, document_id),
        ),
        WorkspaceId.OPTIMIZATION: lambda: make_legacy(
            WorkspaceId.OPTIMIZATION,
            lambda: OptimizationWorkspaceWindow(repository, document_id),
        ),
    }

    shell = WorkflowShellWindow(build_canonical_workspace_registrations(factories))
    shell_holder["shell"] = shell
    registry.set_deep_link_handler(shell.handle_deep_link)

    controller = CommandPaletteController(
        shell,
        registry,
        context_provider=lambda: CommandContext(shell.current_workspace_id.value),
    )
    shell.command_registry = registry  # type: ignore[attr-defined]
    shell.command_palette_controller = controller  # type: ignore[attr-defined]
    return shell


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HTDT native CAD editor")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--document-id", default=F1_DOCUMENT_ID)
    parser.add_argument(
        "--workflow-shell",
        action="store_true",
        help="launch the UX110 workflow shell preview instead of the accepted legacy composition",
    )
    maintenance = parser.add_mutually_exclusive_group()
    maintenance.add_argument(
        "--backup",
        type=Path,
        metavar="ARCHIVE",
        help="create a validated .htdt-backup archive and exit",
    )
    maintenance.add_argument(
        "--restore",
        type=Path,
        metavar="ARCHIVE",
        help="restore a validated .htdt-backup archive and exit",
    )
    maintenance.add_argument(
        "--seed-synthetic-demo",
        action="store_true",
        help="seed an explicitly synthetic O10-O80 development demo and exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    guard = SingleInstanceGuard(args.data_dir)
    if not guard.acquire():
        print(
            "HTDT data directory is already in use by another process: "
            f"{args.data_dir}",
            file=sys.stderr,
        )
        return 2

    try:
        if args.backup is not None:
            manifest = create_backup(args.data_dir, args.backup)
            print(
                f"backup created: {args.backup} "
                f"(schema={manifest.schema_version}, files={len(manifest.files)})"
            )
            return 0
        if args.restore is not None:
            manifest, pre_restore = restore_backup(args.data_dir, args.restore)
            suffix = "" if pre_restore is None else f" · pre-restore backup: {pre_restore}"
            print(
                f"backup restored: {args.restore} "
                f"(schema={manifest.schema_version}, files={len(manifest.files)}){suffix}"
            )
            return 0
        if args.seed_synthetic_demo:
            repository = SceneRepository(args.data_dir / "cad-scenes.sqlite3")
            result = seed_synthetic_optimization_demo(repository)
            print(
                "synthetic demo seeded: "
                f"document={result.document_id} "
                f"search={result.search_spec_id} "
                f"validation={result.validation_id} "
                f"adaptive={result.adaptive_plan_id} "
                f"extended={result.extended_search_id} "
                f"adaptive-extended={result.adaptive_extended_plan_id}"
            )
            print("synthetic demo is development-only and does not unlock owned-room recommendation")
            return 0

        app = QApplication([sys.argv[0]])
        if args.workflow_shell:
            apply_dark_theme(app)
        repository = SceneRepository(args.data_dir / "cad-scenes.sqlite3")
        window = (
            build_workflow_shell(repository, args.document_id)
            if args.workflow_shell
            else OptimizationWorkspaceWindow(repository, args.document_id)
        )
        window.show()
        return int(app.exec())
    finally:
        guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
