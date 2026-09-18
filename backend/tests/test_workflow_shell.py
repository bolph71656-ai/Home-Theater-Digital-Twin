from __future__ import annotations

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QLabel

from htdt.workflow_shell import (
    WorkflowShellWindow,
    WorkspaceId,
    WorkspaceMount,
    build_canonical_workspace_registrations,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


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

    registrations = build_canonical_workspace_registrations(
        {workspace_id: factory(workspace_id) for workspace_id in WorkspaceId}
    )
    window = WorkflowShellWindow(registrations)
    app.processEvents()

    assert window.navigation_labels == ('概要', '部屋', '測定', '最適化')
    assert window.current_workspace_id is WorkspaceId.OVERVIEW
    assert created == [WorkspaceId.OVERVIEW]

    window.navigate(WorkspaceId.ROOM)
    app.processEvents()

    assert window.current_workspace_id is WorkspaceId.ROOM
    assert created == [WorkspaceId.OVERVIEW, WorkspaceId.ROOM]
    assert window.context_labels == ('形状', '物体', 'スピーカー・座席', '音響')
    assert context_events[WorkspaceId.ROOM] == ['geometry']

    window.select_context('acoustics')
    assert context_events[WorkspaceId.ROOM] == ['geometry', 'acoustics']

    window.navigate(WorkspaceId.MEASUREMENT)
    assert window.context_labels == ('読み込み', '割り当て', '品質', '比較')
    assert context_events[WorkspaceId.MEASUREMENT] == ['import']

    window.navigate(WorkspaceId.OPTIMIZATION)
    assert window.context_labels == ('探索設定', '候補', '目的', '測定計画', '検証')
    assert context_events[WorkspaceId.OPTIMIZATION] == ['setup']

    window.close()
    window.deleteLater()
    app.processEvents()


def test_workspace_mount_lifecycle_is_owned_by_router_not_domain_state() -> None:
    app = _app()
    events: list[str] = []

    def factory(workspace_id: WorkspaceId):
        def build() -> WorkspaceMount:
            return WorkspaceMount(
                widget=QLabel(workspace_id.value),
                on_activate=lambda: events.append(f'activate:{workspace_id.value}'),
                on_deactivate=lambda: events.append(f'deactivate:{workspace_id.value}'),
                on_close=lambda: events.append(f'close:{workspace_id.value}'),
            )

        return build

    registrations = build_canonical_workspace_registrations(
        {workspace_id: factory(workspace_id) for workspace_id in WorkspaceId}
    )
    window = WorkflowShellWindow(registrations)
    window.navigate(WorkspaceId.ROOM)
    window.navigate(WorkspaceId.OVERVIEW)
    window.close()
    app.processEvents()

    assert events[:4] == [
        'activate:overview',
        'deactivate:overview',
        'activate:room',
        'deactivate:room',
    ]
    assert 'close:overview' in events
    assert 'close:room' in events

    window.deleteLater()
    app.processEvents()
