from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from htdt.workflow_navigation import WorkspaceDeepLink, WorkspaceId
from htdt.workflow_shell import (
    WorkflowShellWindow,
    WorkspaceMount,
    build_canonical_workspace_registrations,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _registrations(factory):
    return build_canonical_workspace_registrations(
        {workspace_id: factory(workspace_id) for workspace_id in WorkspaceId}
    )


def test_workflow_shell_routes_canonical_workspaces_lazily() -> None:
    app = _app()
    created: list[WorkspaceId] = []
    context_events: dict[WorkspaceId, list[str]] = {workspace_id: [] for workspace_id in WorkspaceId}

    def factory(workspace_id: WorkspaceId):
        def build() -> WorkspaceMount:
            created.append(workspace_id)
            return WorkspaceMount.from_widget(
                QLabel(workspace_id.value),
                on_context_changed=context_events[workspace_id].append,
            )

        return build

    window = WorkflowShellWindow(_registrations(factory))
    app.processEvents()

    assert window.navigation_labels == ("概要", "部屋", "測定", "最適化")
    assert window.current_workspace_id is WorkspaceId.OVERVIEW
    assert created == [WorkspaceId.OVERVIEW]

    assert window.navigate(WorkspaceId.ROOM)
    assert window.context_labels == ("形状", "物体", "スピーカー・座席", "音響")
    assert context_events[WorkspaceId.ROOM] == ["geometry"]

    window.select_context("acoustics")
    assert context_events[WorkspaceId.ROOM] == ["geometry", "acoustics"]

    assert window.handle_deep_link(WorkspaceDeepLink(WorkspaceId.MEASUREMENT, "quality"))
    assert window.current_workspace_id is WorkspaceId.MEASUREMENT
    assert context_events[WorkspaceId.MEASUREMENT][-1] == "quality"

    assert window.navigate(WorkspaceId.OPTIMIZATION)
    assert window.context_labels == ("探索設定", "候補", "比較", "測定・検証")
    assert context_events[WorkspaceId.OPTIMIZATION][-1] == "setup"

    window.close()
    window.deleteLater()
    app.processEvents()


def test_navigation_fails_closed_when_current_workspace_refuses_deactivation() -> None:
    app = _app()
    blocked = {"value": False}

    def factory(workspace_id: WorkspaceId):
        def build() -> WorkspaceMount:
            guard = None
            if workspace_id is WorkspaceId.ROOM:
                guard = lambda: (
                    (False, "未保存の変更があります")
                    if blocked["value"]
                    else (True, None)
                )
            return WorkspaceMount.from_widget(
                QLabel(workspace_id.value),
                before_deactivate=guard,
            )

        return build

    window = WorkflowShellWindow(_registrations(factory))
    assert window.navigate(WorkspaceId.ROOM)
    blocked["value"] = True

    assert window.navigate(WorkspaceId.MEASUREMENT) is False
    assert window.current_workspace_id is WorkspaceId.ROOM
    assert "未保存" in window.statusBar().currentMessage()

    blocked["value"] = False
    assert window.navigate(WorkspaceId.MEASUREMENT)
    window.close()
    window.deleteLater()
    app.processEvents()


def test_entity_deep_link_is_forwarded_to_workspace_callback() -> None:
    app = _app()
    selected: list[str] = []

    def factory(workspace_id: WorkspaceId):
        def build() -> WorkspaceMount:
            return WorkspaceMount.from_widget(
                QLabel(workspace_id.value),
                on_entity_requested=selected.append,
            )

        return build

    window = WorkflowShellWindow(_registrations(factory))
    target = WorkspaceDeepLink(
        WorkspaceId.ROOM,
        "placement",
        entity_id="speaker-1",
    )
    assert window.handle_deep_link(target)
    assert selected == ["speaker-1"]

    window.close()
    window.deleteLater()
    app.processEvents()
