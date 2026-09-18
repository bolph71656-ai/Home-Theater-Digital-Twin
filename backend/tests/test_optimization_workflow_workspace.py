from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

import htdt.optimization_workflow_workspace as optimization_workflow
from htdt.command_registry import WorkspaceDeepLink, WorkspaceId, default_command_definitions
from htdt.optimization_workflow_workspace import (
    OPTIMIZATION_PAGE_IDS,
    build_optimization_workspace_mount,
    normalize_optimization_page,
)
from htdt.workflow_navigation import CANONICAL_WORKSPACE_CONTEXTS
from htdt.workflow_shell import WorkspaceMount


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


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
