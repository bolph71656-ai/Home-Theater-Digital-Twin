from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class WorkspaceId(StrEnum):
    """Stable global destinations exposed by the workflow-first shell."""

    OVERVIEW = 'overview'
    ROOM = 'room'
    MEASUREMENT = 'measurement'
    OPTIMIZATION = 'optimization'


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """A shell-owned sub-context identifier and its Japanese display label."""

    context_id: str
    label: str


@dataclass(slots=True)
class WorkspaceMount:
    """Boundary between the shell and a concrete workspace implementation.

    The shell owns navigation and layout composition. A workspace owns its widget
    and may opt into lifecycle/context callbacks without exposing domain services
    or SceneRevision/evidence state to the shell.
    """

    widget: QWidget
    on_activate: Callable[[], None] | None = None
    on_deactivate: Callable[[], None] | None = None
    on_context_changed: Callable[[str], None] | None = None
    on_close: Callable[[], None] | None = None

    @classmethod
    def from_widget(
        cls,
        widget: QWidget,
        *,
        on_activate: Callable[[], None] | None = None,
        on_deactivate: Callable[[], None] | None = None,
        on_context_changed: Callable[[str], None] | None = None,
    ) -> 'WorkspaceMount':
        return cls(
            widget=widget,
            on_activate=on_activate,
            on_deactivate=on_deactivate,
            on_context_changed=on_context_changed,
            on_close=widget.close,
        )


WorkspaceFactory: TypeAlias = Callable[[], WorkspaceMount]


@dataclass(frozen=True, slots=True)
class WorkspaceRegistration:
    """Declarative registration consumed by the shell/router."""

    workspace_id: WorkspaceId
    label: str
    factory: WorkspaceFactory
    contexts: tuple[WorkspaceContext, ...] = ()


_CANONICAL_LABELS: Mapping[WorkspaceId, str] = {
    WorkspaceId.OVERVIEW: '概要',
    WorkspaceId.ROOM: '部屋',
    WorkspaceId.MEASUREMENT: '測定',
    WorkspaceId.OPTIMIZATION: '最適化',
}

_CANONICAL_CONTEXTS: Mapping[WorkspaceId, tuple[WorkspaceContext, ...]] = {
    WorkspaceId.OVERVIEW: (),
    WorkspaceId.ROOM: (
        WorkspaceContext('geometry', '形状'),
        WorkspaceContext('objects', '物体'),
        WorkspaceContext('placement', 'スピーカー・座席'),
        WorkspaceContext('acoustics', '音響'),
    ),
    WorkspaceId.MEASUREMENT: (
        WorkspaceContext('import', '読み込み'),
        WorkspaceContext('assignment', '割り当て'),
        WorkspaceContext('quality', '品質'),
        WorkspaceContext('comparison', '比較'),
    ),
    WorkspaceId.OPTIMIZATION: (
        WorkspaceContext('setup', '探索設定'),
        WorkspaceContext('candidates', '候補'),
        WorkspaceContext('objectives', '目的'),
        WorkspaceContext('measurement-plan', '測定計画'),
        WorkspaceContext('validation', '検証'),
    ),
}


def build_canonical_workspace_registrations(
    factories: Mapping[WorkspaceId, WorkspaceFactory],
) -> tuple[WorkspaceRegistration, ...]:
    """Bind concrete factories to the canonical top-level information architecture."""

    missing = tuple(workspace_id for workspace_id in WorkspaceId if workspace_id not in factories)
    if missing:
        names = ', '.join(workspace_id.value for workspace_id in missing)
        raise ValueError(f'missing workspace factories: {names}')

    return tuple(
        WorkspaceRegistration(
            workspace_id=workspace_id,
            label=_CANONICAL_LABELS[workspace_id],
            contexts=_CANONICAL_CONTEXTS[workspace_id],
            factory=factories[workspace_id],
        )
        for workspace_id in WorkspaceId
    )


def make_overview_mount() -> WorkspaceMount:
    """Provide the shell-level Overview landing surface without domain duplication."""

    page = QWidget()
    page.setObjectName('workflowOverview')
    layout = QVBoxLayout(page)
    layout.setContentsMargins(48, 44, 48, 44)
    layout.setSpacing(12)

    title = QLabel('概要')
    title.setObjectName('workflowOverviewTitle')
    layout.addWidget(title)

    description = QLabel('左のメニューから作業を選択してください。部屋の作成、測定、最適化へ移動できます。')
    description.setObjectName('workflowOverviewBody')
    description.setWordWrap(True)
    layout.addWidget(description)
    layout.addStretch(1)

    return WorkspaceMount.from_widget(page)


def _normalize_workspace_id(workspace_id: WorkspaceId | str) -> WorkspaceId:
    return workspace_id if isinstance(workspace_id, WorkspaceId) else WorkspaceId(workspace_id)


class WorkspaceRouter(QStackedWidget):
    """Lazy workspace host; it never interprets domain/service state."""

    def __init__(self, registrations: Iterable[WorkspaceRegistration], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('workflowRouter')
        self._registrations = {registration.workspace_id: registration for registration in registrations}
        if set(self._registrations) != set(WorkspaceId):
            raise ValueError('workflow router requires exactly the four canonical workspace destinations')
        self._mounts: dict[WorkspaceId, WorkspaceMount] = {}
        self._current_workspace_id: WorkspaceId | None = None

    @property
    def current_workspace_id(self) -> WorkspaceId | None:
        return self._current_workspace_id

    def registration(self, workspace_id: WorkspaceId | str) -> WorkspaceRegistration:
        return self._registrations[_normalize_workspace_id(workspace_id)]

    def mount(self, workspace_id: WorkspaceId | str) -> WorkspaceMount | None:
        return self._mounts.get(_normalize_workspace_id(workspace_id))

    def navigate(self, workspace_id: WorkspaceId | str) -> WorkspaceMount:
        destination = _normalize_workspace_id(workspace_id)
        if destination == self._current_workspace_id:
            return self._ensure_mount(destination)

        current = self._mounts.get(self._current_workspace_id) if self._current_workspace_id is not None else None
        if current is not None and current.on_deactivate is not None:
            current.on_deactivate()

        mount = self._ensure_mount(destination)
        self.setCurrentWidget(mount.widget)
        self._current_workspace_id = destination
        if mount.on_activate is not None:
            mount.on_activate()
        return mount

    def select_context(self, workspace_id: WorkspaceId | str, context_id: str) -> None:
        destination = _normalize_workspace_id(workspace_id)
        registration = self._registrations[destination]
        valid_ids = {context.context_id for context in registration.contexts}
        if context_id not in valid_ids:
            raise ValueError(f'unknown context {context_id!r} for workspace {destination.value!r}')

        mount = self._ensure_mount(destination)
        if mount.on_context_changed is not None:
            mount.on_context_changed(context_id)

    def shutdown(self) -> None:
        for mount in tuple(self._mounts.values()):
            if mount.on_close is not None:
                mount.on_close()
            else:
                mount.widget.close()

    def _ensure_mount(self, workspace_id: WorkspaceId) -> WorkspaceMount:
        existing = self._mounts.get(workspace_id)
        if existing is not None:
            return existing

        mount = self._registrations[workspace_id].factory()
        if not isinstance(mount, WorkspaceMount):
            raise TypeError('workspace factory must return WorkspaceMount')
        if mount.widget.parent() is not None:
            raise ValueError('workspace factory must return an unparented widget')

        self._mounts[workspace_id] = mount
        self.addWidget(mount.widget)
        return mount


class WorkflowRail(QFrame):
    """Global navigation only; contextual controls belong above the active workspace."""

    def __init__(
        self,
        registrations: Iterable[WorkspaceRegistration],
        on_navigate: Callable[[WorkspaceId], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName('workflowRail')
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setFixedWidth(184)

        self._buttons: dict[WorkspaceId, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(6)

        brand = QLabel('HTDT')
        brand.setObjectName('workflowBrand')
        layout.addWidget(brand)
        layout.addSpacing(18)

        for registration in registrations:
            button = QPushButton(registration.label)
            button.setObjectName('workflowRailButton')
            button.setCheckable(True)
            button.setProperty('workspaceId', registration.workspace_id.value)
            button.clicked.connect(
                lambda checked=False, workspace_id=registration.workspace_id: on_navigate(workspace_id)
            )
            self._group.addButton(button)
            self._buttons[registration.workspace_id] = button
            layout.addWidget(button)

        layout.addStretch(1)

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(button.text() for button in self._buttons.values())

    def set_active(self, workspace_id: WorkspaceId | str) -> None:
        self._buttons[_normalize_workspace_id(workspace_id)].setChecked(True)


class TopContextBar(QFrame):
    """Displays only the active workspace title and its contextual destinations."""

    def __init__(self, on_context_selected: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('workflowContextBar')
        self._on_context_selected = on_context_selected
        self._context_buttons: dict[str, QPushButton] = {}
        self._context_group: QButtonGroup | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 12, 18, 12)
        layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName('workflowWorkspaceTitle')
        layout.addWidget(self._title)
        layout.addSpacing(12)

        self._context_container = QWidget()
        self._context_container.setObjectName('workflowContextContainer')
        self._context_layout = QHBoxLayout(self._context_container)
        self._context_layout.setContentsMargins(0, 0, 0, 0)
        self._context_layout.setSpacing(4)
        layout.addWidget(self._context_container)
        layout.addStretch(1)

    @property
    def context_labels(self) -> tuple[str, ...]:
        return tuple(button.text() for button in self._context_buttons.values())

    def set_workspace(self, registration: WorkspaceRegistration, selected_context_id: str | None) -> None:
        self._title.setText(registration.label)
        self._clear_contexts()

        if not registration.contexts:
            self._context_container.setVisible(False)
            return

        self._context_container.setVisible(True)
        self._context_group = QButtonGroup(self)
        self._context_group.setExclusive(True)

        for context in registration.contexts:
            button = QPushButton(context.label)
            button.setObjectName('workflowContextButton')
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, context_id=context.context_id: self._on_context_selected(context_id)
            )
            self._context_group.addButton(button)
            self._context_buttons[context.context_id] = button
            self._context_layout.addWidget(button)

        if selected_context_id is not None:
            selected = self._context_buttons.get(selected_context_id)
            if selected is not None:
                selected.setChecked(True)

    def set_active_context(self, context_id: str) -> None:
        button = self._context_buttons.get(context_id)
        if button is None:
            raise ValueError(f'context {context_id!r} is not visible in the current workspace')
        button.setChecked(True)

    def _clear_contexts(self) -> None:
        if self._context_group is not None:
            self._context_group.deleteLater()
            self._context_group = None
        self._context_buttons.clear()

        while self._context_layout.count():
            item = self._context_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class WorkflowShellWindow(QMainWindow):
    """Workflow-first product shell around independently replaceable workspaces."""

    def __init__(
        self,
        registrations: Iterable[WorkspaceRegistration],
        *,
        initial_workspace: WorkspaceId = WorkspaceId.OVERVIEW,
    ) -> None:
        super().__init__()
        self.setObjectName('workflowShell')
        self.setWindowTitle('Home Theater Digital Twin')

        registration_tuple = tuple(registrations)
        self._registrations = {registration.workspace_id: registration for registration in registration_tuple}
        if set(self._registrations) != set(WorkspaceId):
            raise ValueError('workflow shell requires exactly the four canonical workspace destinations')

        self._selected_context: dict[WorkspaceId, str] = {}
        for registration in registration_tuple:
            if registration.contexts:
                self._selected_context[registration.workspace_id] = registration.contexts[0].context_id

        root = QWidget()
        root.setObjectName('workflowShellRoot')
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.rail = WorkflowRail(registration_tuple, self.navigate)
        root_layout.addWidget(self.rail)

        content = QFrame()
        content.setObjectName('workflowContent')
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.context_bar = TopContextBar(self._select_current_context)
        content_layout.addWidget(self.context_bar)

        self.router = WorkspaceRouter(registration_tuple)
        content_layout.addWidget(self.router, 1)

        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self.resize(1440, 900)
        self.setStyleSheet(_SHELL_STYLE)
        self.navigate(initial_workspace)

    @property
    def current_workspace_id(self) -> WorkspaceId:
        current = self.router.current_workspace_id
        if current is None:
            raise RuntimeError('workflow shell has not selected a workspace')
        return current

    @property
    def navigation_labels(self) -> tuple[str, ...]:
        return self.rail.labels

    @property
    def context_labels(self) -> tuple[str, ...]:
        return self.context_bar.context_labels

    def navigate(self, workspace_id: WorkspaceId | str) -> None:
        destination = _normalize_workspace_id(workspace_id)
        registration = self._registrations[destination]
        self.router.navigate(destination)
        self.rail.set_active(destination)

        selected_context = self._selected_context.get(destination)
        self.context_bar.set_workspace(registration, selected_context)
        if selected_context is not None:
            self.router.select_context(destination, selected_context)

    def select_context(self, context_id: str) -> None:
        self._select_current_context(context_id)

    def _select_current_context(self, context_id: str) -> None:
        workspace_id = self.current_workspace_id
        self.router.select_context(workspace_id, context_id)
        self._selected_context[workspace_id] = context_id
        self.context_bar.set_active_context(context_id)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.router.shutdown()
        super().closeEvent(event)


_SHELL_STYLE = """
QWidget#workflowShellRoot,
QFrame#workflowContent,
QStackedWidget#workflowRouter {
    background: #111318;
    color: #f1f3f5;
}
QFrame#workflowRail {
    background: #171a20;
    border-right: 1px solid #2a2e36;
}
QLabel#workflowBrand {
    color: #f4f6f8;
    font-size: 18px;
    font-weight: 700;
    padding: 4px 8px;
}
QPushButton#workflowRailButton {
    background: transparent;
    border: 0;
    border-radius: 8px;
    color: #aeb4bf;
    font-size: 14px;
    padding: 10px 12px;
    text-align: left;
}
QPushButton#workflowRailButton:hover {
    background: #20242c;
    color: #eef1f5;
}
QPushButton#workflowRailButton:checked {
    background: #292f3a;
    color: #ffffff;
    font-weight: 600;
}
QFrame#workflowContextBar {
    background: #171a20;
    border-bottom: 1px solid #2a2e36;
}
QLabel#workflowWorkspaceTitle {
    color: #f4f6f8;
    font-size: 16px;
    font-weight: 650;
}
QPushButton#workflowContextButton {
    background: transparent;
    border: 0;
    border-radius: 7px;
    color: #aeb4bf;
    padding: 7px 10px;
}
QPushButton#workflowContextButton:hover {
    background: #20242c;
    color: #eef1f5;
}
QPushButton#workflowContextButton:checked {
    background: #2b313b;
    color: #ffffff;
}
QWidget#workflowOverview {
    background: #111318;
}
QLabel#workflowOverviewTitle {
    color: #f4f6f8;
    font-size: 26px;
    font-weight: 700;
}
QLabel#workflowOverviewBody {
    color: #aeb4bf;
    font-size: 14px;
}
"""
