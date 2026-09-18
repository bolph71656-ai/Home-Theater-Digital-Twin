from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

import htdt.optimization_workflow_workspace as optimization_workflow
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import F1_DOCUMENT_ID
from htdt.command_registry import WorkspaceDeepLink, WorkspaceId, default_command_definitions
from htdt.optimization_workflow_workspace import (
    OPTIMIZATION_PAGE_IDS,
    OptimizationWorkflowWorkspace,
    build_optimization_workspace_mount,
    normalize_optimization_page,
)
from htdt.workflow_navigation import CANONICAL_WORKSPACE_CONTEXTS
from htdt.workflow_shell import WorkspaceMount


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])




class _FakePlotter:
    def add_mesh(self, *_args, **_kwargs):
        return object()

    def remove_actor(self, *_args, **_kwargs) -> None:
        pass

    def add_text(self, *_args, **_kwargs) -> None:
        pass

    def render(self) -> None:
        pass


class FakeOptimizationViewport(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.plotter = _FakePlotter()
        self.render_calls: list[tuple[str | None, bool]] = []

    def render_document(
        self,
        document,
        *,
        selected_id: str | None,
        overlays,
        reset_camera: bool = False,
    ) -> None:
        self.render_calls.append((selected_id, reset_camera))


def test_ux140_uses_four_canonical_optimization_pages() -> None:
    contexts = CANONICAL_WORKSPACE_CONTEXTS[WorkspaceId.OPTIMIZATION]

    assert OPTIMIZATION_PAGE_IDS == ("setup", "candidates", "comparison", "validation")
    assert tuple(context.context_id for context in contexts) == OPTIMIZATION_PAGE_IDS
    assert tuple(context.label for context in contexts) == (
        "探索設定",
        "候補",
        "比較",
        "測定・検証",
    )


def test_ux140_accepts_legacy_optimization_deep_link_sections() -> None:
    assert normalize_optimization_page("objectives") == "comparison"
    assert normalize_optimization_page("measurement-plan") == "validation"
    assert normalize_optimization_page("comparison") == "comparison"


def test_candidate_compare_command_targets_comparison_page() -> None:
    definition = next(
        item
        for item in default_command_definitions()
        if item.command_id == "optimization.compare_candidates"
    )

    assert definition.deep_link == WorkspaceDeepLink(
        WorkspaceId.OPTIMIZATION,
        "comparison",
    )


def test_ux140_real_workspace_has_no_legacy_mainwindow_or_docks(tmp_path) -> None:
    app = _app()
    repository = SceneRepository(tmp_path / "scenes.sqlite3")
    workspace = OptimizationWorkflowWorkspace(
        repository,
        F1_DOCUMENT_ID,
        viewport_factory=lambda parent: FakeOptimizationViewport(parent),
    )

    assert not isinstance(workspace, QMainWindow)
    assert workspace.findChildren(QDockWidget) == []
    assert workspace.page_ids == ("setup", "candidates", "comparison", "validation")
    assert workspace.controller.__class__.__name__ == "OptimizationWorkflowController"
    assert workspace.controller.rew_combo is not None
    assert workspace.controller.campaign_measurement_point_combo is not None

    workspace.controller.scene.add_object("measurement_point")
    allowed, reason = workspace.before_deactivate()
    assert allowed is False
    assert reason is not None and "未保存" in reason

    workspace.close()
    workspace.deleteLater()
    app.processEvents()


def test_ux140_builder_exposes_shell_mount_contract(monkeypatch) -> None:
    app = _app()

    class FakeOptimizationWorkspace(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.sections: list[str] = []

        def select_section(self, section_id: str) -> None:
            self.sections.append(section_id)

        def refresh_from_authorities(self) -> None:
            pass

        def activate(self) -> None:
            pass

        def before_deactivate(self) -> tuple[bool, str | None]:
            return True, None

    workspace = FakeOptimizationWorkspace()
    monkeypatch.setattr(
        optimization_workflow,
        "OptimizationWorkflowWorkspace",
        lambda _repository, _document_id: workspace,
    )

    mount = build_optimization_workspace_mount(object(), "document-1")

    assert isinstance(mount, WorkspaceMount)
    assert mount.widget is workspace
    assert mount.on_context_changed is not None
    mount.on_context_changed("comparison")
    assert workspace.sections == ["comparison"]

    workspace.close()
    workspace.deleteLater()
    app.processEvents()
