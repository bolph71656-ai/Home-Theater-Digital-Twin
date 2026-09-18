from __future__ import annotations

from typing import TypeVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from .cad_repository import SceneRepository
from .cad_scene import F1_DOCUMENT_ID
from .optimization_workspace import OptimizationWorkspaceWindow
from .ui_theme import (
    ControlSize,
    SurfaceRole,
    TypographyRole,
    set_control_size,
    set_primary_action,
    set_surface_role,
    set_typography_role,
)
from .workflow_legacy_bridge import (
    legacy_editor_deactivation_guard,
    refresh_legacy_editor_revision,
)
from .workflow_shell import WorkspaceMount


OPTIMIZATION_PAGE_IDS = ("setup", "candidates", "comparison", "validation")
_OPTIMIZATION_PAGE_ALIASES = {
    "objectives": "comparison",
    "measurement-plan": "validation",
}


def normalize_optimization_page(value: str) -> str:
    normalized = _OPTIMIZATION_PAGE_ALIASES.get(value, value)
    if normalized not in OPTIMIZATION_PAGE_IDS:
        raise ValueError(f"unknown optimization page: {value!r}")
    return normalized


TWidget = TypeVar("TWidget", bound=QWidget)


def _required(widget: TWidget | None, name: str) -> TWidget:
    if widget is None:
        raise RuntimeError(f"optimization controller did not create {name}")
    return widget


def _heading(title: str, description: str | None = None) -> QWidget:
    frame = QFrame()
    set_surface_role(frame, SurfaceRole.BASE)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    label = QLabel(title)
    set_typography_role(label, TypographyRole.WORKSPACE_TITLE)
    layout.addWidget(label)
    if description:
        detail = QLabel(description)
        detail.setWordWrap(True)
        set_typography_role(detail, TypographyRole.SECONDARY)
        layout.addWidget(detail)
    return frame


def _card(title: str, description: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    set_surface_role(frame, SurfaceRole.RAISED)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)

    label = QLabel(title)
    set_typography_role(label, TypographyRole.SECTION_TITLE)
    layout.addWidget(label)
    if description:
        detail = QLabel(description)
        detail.setWordWrap(True)
        set_typography_role(detail, TypographyRole.SECONDARY)
        layout.addWidget(detail)
    return frame, layout


def _scroll_page(body: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(body)
    return scroll


def _button(label: str, callback, *, primary: bool = False) -> QPushButton:
    button = QPushButton(label)
    set_control_size(button, ControlSize.STANDARD)
    if primary:
        set_primary_action(button)
    button.clicked.connect(callback)
    return button


def _advanced_block(
    label: str,
    description: str,
    content: QWidget,
    *,
    expanded: bool = False,
) -> QWidget:
    frame = QFrame()
    set_surface_role(frame, SurfaceRole.RAISED)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 14)
    layout.setSpacing(8)

    toggle = QPushButton(label)
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    set_control_size(toggle, ControlSize.COMPACT)
    layout.addWidget(toggle)

    detail = QLabel(description)
    detail.setWordWrap(True)
    set_typography_role(detail, TypographyRole.SECONDARY)
    layout.addWidget(detail)

    content.setVisible(expanded)
    toggle.toggled.connect(content.setVisible)
    layout.addWidget(content)
    return frame


class OptimizationWorkflowWorkspace(OptimizationWorkspaceWindow):
    """UX140 page-first composition over the existing O10-O80 controller authority.

    The inherited optimization window remains the execution/state adapter for the
    accepted SearchSpec, objective/Pareto, measurement-plan, validation, adaptive,
    and extended-search controllers. This class only recomposes their existing
    controls into task pages and does not introduce optimization semantics.
    """

    def __init__(
        self,
        repository: SceneRepository,
        document_id: str = F1_DOCUMENT_ID,
    ) -> None:
        super().__init__(repository, document_id)
        self.setWindowTitle("Home Theater Digital Twin — 最適化")
        self._optimization_stack = QStackedWidget()
        self._optimization_pages: dict[str, QWidget] = {}
        self._install_workflow_surface()
        self.select_section("setup")

    @property
    def page_ids(self) -> tuple[str, ...]:
        return OPTIMIZATION_PAGE_IDS

    @property
    def current_page_id(self) -> str:
        current = self._optimization_stack.currentWidget()
        for page_id, page in self._optimization_pages.items():
            if page is current:
                return page_id
        raise RuntimeError("optimization page stack has no active page")

    def select_section(self, section_id: str) -> None:
        page_id = normalize_optimization_page(section_id)
        self._optimization_stack.setCurrentWidget(self._optimization_pages[page_id])
        if page_id == "validation":
            self.refresh_measurement_plans()
            self.refresh_validation_campaigns()
            self.refresh_model_validations()
            self.refresh_adaptive_plans()
            self.refresh_adaptive_extended_plans()

    def refresh_from_authorities(self) -> None:
        """Refresh visible data through the existing O-series repositories/services."""
        self._refresh_search_entities()
        self._refresh_search_specs()
        self._refresh_extended_entities()
        self._refresh_extended_capabilities()
        self._refresh_extended_specs()
        self.refresh_measurement_plans()
        self.refresh_validation_campaigns()
        self.refresh_model_validations()
        self.refresh_adaptive_plans()
        self.refresh_adaptive_extended_plans()

    def _install_workflow_surface(self) -> None:
        viewport_widget = self.takeCentralWidget()
        if viewport_widget is None:
            raise RuntimeError("optimization controller did not provide a viewport")

        # Legacy docks/toolbars remain alive because controller methods own widgets
        # and state there, but the UX140 surface no longer exposes that composition.
        for dock in self.findChildren(QDockWidget):
            dock.hide()
        for toolbar in self.findChildren(QToolBar):
            toolbar.hide()

        root = QWidget()
        set_surface_role(root, SurfaceRole.BASE)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(12)
        root_layout.addWidget(self._optimization_stack, 1)
        self.setCentralWidget(root)

        pages = {
            "setup": self._build_setup_page(),
            "candidates": self._build_candidates_page(viewport_widget),
            "comparison": self._build_comparison_page(),
            "validation": self._build_validation_page(),
        }
        for page_id in OPTIMIZATION_PAGE_IDS:
            page = pages[page_id]
            page.setObjectName(f"optimizationPage:{page_id}")
            self._optimization_pages[page_id] = page
            self._optimization_stack.addWidget(page)

    def _build_setup_page(self) -> QWidget:
        body = QWidget()
        set_surface_role(body, SurfaceRole.BASE)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 12)
        layout.setSpacing(12)
        layout.addWidget(
            _heading(
                "探索設定",
                "保存済みの部屋・配置と制約に探索範囲を結び付けます。候補生成の前提だけをここで定義します。",
            )
        )

        search_card, search = _card(
            "位置の探索範囲",
            "候補はhard constraintを満たす幾何配置です。ここでは順位や推薦を決めません。",
        )
        form = QFormLayout()
        form.addRow("名前", _required(self.search_name_field, "search_name_field"))
        form.addRow("可動物体", _required(self.search_entity_combo, "search_entity_combo"))
        form.addRow("軸", _required(self.search_axis_combo, "search_axis_combo"))
        form.addRow("最小", _required(self.search_min_field, "search_min_field"))
        form.addRow("最大", _required(self.search_max_field, "search_max_field"))
        form.addRow("刻み", _required(self.search_step_field, "search_step_field"))
        form.addRow("候補上限", _required(self.search_limit_field, "search_limit_field"))
        search.addLayout(form)

        axis_actions = QHBoxLayout()
        axis_actions.addWidget(_button("軸を追加 / 更新", self.add_search_axis))
        axis_actions.addWidget(_button("選択軸を削除", self.remove_selected_search_axis))
        axis_actions.addStretch(1)
        search.addLayout(axis_actions)
        search.addWidget(_required(self.search_axis_tree, "search_axis_tree"))

        binding = _required(self.search_binding_label, "search_binding_label")
        binding.setWordWrap(True)
        search.addWidget(binding)
        save_button = _required(self.search_save_button, "search_save_button")
        set_primary_action(save_button)
        search.addWidget(save_button)

        specs_card, specs = _card(
            "保存済み探索設定",
            "SceneRevisionまたは制約が変わった設定はstaleとして扱われ、候補生成には使われません。",
        )
        specs.addWidget(_required(self.search_spec_tree, "search_spec_tree"))
        layout.addWidget(search_card)
        layout.addWidget(specs_card)

        extended_content = QWidget()
        extended_layout = QVBoxLayout(extended_content)
        extended_layout.setContentsMargins(0, 4, 0, 0)
        extended_layout.setSpacing(10)

        capability_row = QHBoxLayout()
        capability_row.addWidget(_required(self.extended_capability_combo, "extended_capability_combo"), 1)
        capability_row.addWidget(
            _button("Synthetic capability", self.create_synthetic_extended_capability)
        )
        capability_row.addWidget(
            _button("選択O60から本番capability", self.create_owned_room_extended_capability)
        )
        extended_layout.addLayout(capability_row)

        extended_form = QFormLayout()
        extended_form.addRow(
            "parameter",
            _required(self.extended_parameter_combo, "extended_parameter_combo"),
        )
        extended_form.addRow(
            "speaker",
            _required(self.extended_entity_combo, "extended_entity_combo"),
        )
        extended_form.addRow("最小", _required(self.extended_min_field, "extended_min_field"))
        extended_form.addRow("最大", _required(self.extended_max_field, "extended_max_field"))
        extended_form.addRow("刻み", _required(self.extended_step_field, "extended_step_field"))
        extended_form.addRow(
            "候補上限",
            _required(self.extended_limit_field, "extended_limit_field"),
        )
        extended_layout.addLayout(extended_form)

        extended_axis_actions = QHBoxLayout()
        extended_axis_actions.addWidget(
            _button("軸を追加 / 更新", self.add_or_update_extended_axis)
        )
        extended_axis_actions.addWidget(
            _button("選択軸を削除", self.remove_selected_extended_axis)
        )
        extended_axis_actions.addStretch(1)
        extended_layout.addLayout(extended_axis_actions)
        extended_layout.addWidget(_required(self.extended_axis_tree, "extended_axis_tree"))
        extended_layout.addWidget(
            _button("Extended SearchSpecを保存", self.save_extended_search_spec, primary=True)
        )
        extended_layout.addWidget(_required(self.extended_spec_tree, "extended_spec_tree"))

        layout.addWidget(
            _advanced_block(
                "詳細: 向き・toe-inを探索",
                "O80 capabilityが明示された場合だけacoustic aim / physical body yawを追加探索します。"
                " Syntheticとowned-roomのscopeは既存authorityのまま分離されます。",
                extended_content,
            )
        )
        layout.addStretch(1)
        return _scroll_page(body)

    def _build_candidates_page(self, viewport_widget: QWidget) -> QWidget:
        page = QWidget()
        set_surface_role(page, SurfaceRole.BASE)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(
            _heading(
                "候補",
                "候補を生成して3Dで確認します。previewはSceneを変更せず、明示的な適用だけが編集履歴に入ります。",
            )
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        viewport_frame = QFrame()
        set_surface_role(viewport_frame, SurfaceRole.CANVAS)
        viewport_layout = QVBoxLayout(viewport_frame)
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        viewport_layout.addWidget(viewport_widget)
        splitter.addWidget(viewport_frame)

        side_body = QWidget()
        set_surface_role(side_body, SurfaceRole.BASE)
        side = QVBoxLayout(side_body)
        side.setContentsMargins(12, 4, 4, 8)
        side.setSpacing(10)

        base_card, base = _card(
            "位置候補",
            "現在選択中のSearchSpecからO10候補を生成します。",
        )
        generation = QHBoxLayout()
        generation.addWidget(_required(self.search_generate_button, "search_generate_button"))
        generation.addWidget(_required(self.search_cancel_button, "search_cancel_button"))
        base.addLayout(generation)
        summary = _required(self.search_summary_label, "search_summary_label")
        summary.setWordWrap(True)
        base.addWidget(summary)
        base.addWidget(_required(self.search_candidate_tree, "search_candidate_tree"), 1)

        paging = QHBoxLayout()
        paging.addWidget(_required(self.search_prev_button, "search_prev_button"))
        paging.addWidget(_required(self.search_next_button, "search_next_button"))
        base.addLayout(paging)

        actions = QHBoxLayout()
        actions.addWidget(_required(self.search_preview_button, "search_preview_button"))
        actions.addWidget(
            _required(self.search_clear_preview_button, "search_clear_preview_button")
        )
        apply_button = _required(self.search_apply_button, "search_apply_button")
        set_primary_action(apply_button)
        actions.addWidget(apply_button)
        base.addLayout(actions)
        side.addWidget(base_card)

        extended_content = QWidget()
        extended = QVBoxLayout(extended_content)
        extended.setContentsMargins(0, 4, 0, 0)
        extended.setSpacing(8)
        extended_generation = QHBoxLayout()
        extended_generation.addWidget(
            _required(self.extended_generate_button, "extended_generate_button")
        )
        extended_generation.addWidget(
            _required(self.extended_cancel_button, "extended_cancel_button")
        )
        extended.addLayout(extended_generation)
        extended_summary = _required(self.extended_summary_label, "extended_summary_label")
        extended_summary.setWordWrap(True)
        extended.addWidget(extended_summary)
        extended.addWidget(
            _required(self.extended_candidate_tree, "extended_candidate_tree")
        )
        extended_paging = QHBoxLayout()
        extended_paging.addWidget(_required(self.extended_prev_button, "extended_prev_button"))
        extended_paging.addWidget(_required(self.extended_next_button, "extended_next_button"))
        extended.addLayout(extended_paging)
        extended_actions = QHBoxLayout()
        extended_actions.addWidget(
            _required(self.extended_preview_button, "extended_preview_button")
        )
        extended_actions.addWidget(
            _required(self.extended_clear_preview_button, "extended_clear_preview_button")
        )
        extended_apply = _required(self.extended_apply_button, "extended_apply_button")
        set_primary_action(extended_apply)
        extended_actions.addWidget(extended_apply)
        extended.addLayout(extended_actions)

        side.addWidget(
            _advanced_block(
                "詳細: Extended候補",
                "O80 SearchSpecがある場合に位置と向きの候補を同じauthorityで確認します。",
                extended_content,
            )
        )
        side.addStretch(1)

        side_scroll = _scroll_page(side_body)
        side_scroll.setMinimumWidth(430)
        side_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        splitter.addWidget(side_scroll)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return page

    def _build_comparison_page(self) -> QWidget:
        body = QWidget()
        set_surface_role(body, SurfaceRole.BASE)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 12)
        layout.setSpacing(12)
        layout.addWidget(
            _heading(
                "比較",
                "候補ごとのobjectiveを独立した指標として比較します。総合点や新しい推薦順位は作りません。",
            )
        )

        metrics_card, metrics = _card(
            "比較する指標",
            "同じobjective集合・単位のevidenceだけを既存O30/Pareto authorityで比較します。",
        )
        metrics.addWidget(_required(self.objective_list, "objective_list"))
        refresh = _required(self.pareto_refresh_button, "pareto_refresh_button")
        set_primary_action(refresh)
        metrics.addWidget(refresh)
        summary = _required(self.pareto_summary_label, "pareto_summary_label")
        summary.setWordWrap(True)
        metrics.addWidget(summary)

        pareto_card, pareto = _card(
            "Pareto比較",
            "「非劣」は複数指標で他候補に支配されないことを示し、音質の総合順位や自動推薦ではありません。",
        )
        pareto.addWidget(_required(self.pareto_tree, "pareto_tree"), 1)

        layout.addWidget(metrics_card)
        layout.addWidget(pareto_card, 1)
        return body

    def _build_validation_page(self) -> QWidget:
        body = QWidget()
        set_surface_role(body, SurfaceRole.BASE)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 12)
        layout.setSpacing(12)
        layout.addWidget(
            _heading(
                "測定・検証",
                "候補を実測へ結び付け、事前登録したValidation Campaignで検証します。"
                " ProductionとSyntheticのevidence境界は既存O60〜O80 authorityに従います。",
            )
        )

        measure_card, measure = _card(
            "測定計画",
            "適用・保存した候補と、その正確なSceneRevisionに一致するmeasured evidenceだけを関連付けます。",
        )
        measure_button = _required(self.measurement_plan_button, "measurement_plan_button")
        measure.addWidget(measure_button)
        plan_label = _required(self.measurement_plan_label, "measurement_plan_label")
        plan_label.setWordWrap(True)
        measure.addWidget(plan_label)
        measure.addWidget(_required(self.measurement_plan_tree, "measurement_plan_tree"))
        measure.addWidget(_required(self.measurement_match_list, "measurement_match_list"))
        complete = _required(self.measurement_complete_button, "measurement_complete_button")
        set_primary_action(complete)
        measure.addWidget(complete)
        layout.addWidget(measure_card)

        campaign_card, campaign = _card(
            "Validation Campaign",
            "測定結果を見る前にcalibration / holdout、帯域、閾値を固定します。",
        )
        assignment = QHBoxLayout()
        assignment.addWidget(
            _button(
                "選択候補 → calibration",
                lambda: self.assign_selected_candidate_to_campaign("calibration"),
            )
        )
        assignment.addWidget(
            _button(
                "選択候補 → holdout",
                lambda: self.assign_selected_candidate_to_campaign("holdout"),
            )
        )
        assignment.addWidget(
            _button("割り当て解除", self.remove_selected_campaign_assignment)
        )
        assignment.addStretch(1)
        campaign.addLayout(assignment)
        campaign.addWidget(_required(self.campaign_assignment_tree, "campaign_assignment_tree"))

        campaign_form = QFormLayout()
        campaign_form.addRow(
            "model version",
            _required(self.campaign_model_version_field, "campaign_model_version_field"),
        )
        campaign_form.addRow(
            "検証帯域 low Hz",
            _required(self.campaign_low_field, "campaign_low_field"),
        )
        campaign_form.addRow(
            "検証帯域 high Hz",
            _required(self.campaign_high_field, "campaign_high_field"),
        )
        campaign_form.addRow(
            "holdout RMS上限 dB",
            _required(self.campaign_residual_field, "campaign_residual_field"),
        )
        campaign_form.addRow(
            "感度上限 dB/m",
            _required(self.campaign_sensitivity_field, "campaign_sensitivity_field"),
        )
        campaign_form.addRow(
            "感度誤差上限 dB/m",
            _required(
                self.campaign_sensitivity_error_field,
                "campaign_sensitivity_error_field",
            ),
        )
        campaign_form.addRow(
            "候補差 / repeatability",
            _required(self.campaign_separation_field, "campaign_separation_field"),
        )
        campaign.addLayout(campaign_form)
        campaign.addWidget(
            _button(
                "Campaignを測定前に保存",
                self.save_validation_campaign,
                primary=True,
            )
        )
        campaign.addWidget(_required(self.campaign_tree, "campaign_tree"))

        campaign_actions = QHBoxLayout()
        campaign_actions.addWidget(_button("readiness更新", self.refresh_validation_campaigns))
        campaign_actions.addWidget(
            _button("O30 objective evidence生成", self.materialize_selected_campaign_objectives)
        )
        campaign_actions.addWidget(
            _button("選択REW → Campaign実測", self.read_selected_rew_for_campaign_async)
        )
        campaign.addLayout(campaign_actions)
        detail = _required(self.campaign_detail_label, "campaign_detail_label")
        detail.setWordWrap(True)
        campaign.addWidget(detail)

        applicability = QFormLayout()
        for code, label in (("geometry", "geometry"), ("band", "band"), ("routing", "routing")):
            state: QComboBox = self.campaign_applicability_state[code]
            evidence = self.campaign_applicability_detail[code]
            applicability.addRow(f"{label} 判定", state)
            applicability.addRow(f"{label} 根拠", evidence)
        campaign.addLayout(applicability)
        campaign.addWidget(
            _button(
                "ValidationRecordを構築・保存",
                self.build_and_save_selected_campaign_validation,
                primary=True,
            )
        )
        layout.addWidget(campaign_card)

        validation_card, validation = _card(
            "保存済み検証",
            "residual / trend / sensitivity / repeatability / applicabilityと既存recommendation gateをそのまま表示します。",
        )
        validation.addWidget(
            _required(self.validation_refresh_button, "validation_refresh_button")
        )
        validation.addWidget(_required(self.validation_tree, "validation_tree"))
        validation_detail = _required(self.validation_detail_label, "validation_detail_label")
        validation_detail.setWordWrap(True)
        validation.addWidget(validation_detail)
        layout.addWidget(validation_card)

        adaptive_content = QWidget()
        adaptive = QVBoxLayout(adaptive_content)
        adaptive.setContentsMargins(0, 4, 0, 0)
        adaptive.setSpacing(10)
        adaptive_form = QFormLayout()
        adaptive_form.addRow(
            "実行scope",
            _required(self.adaptive_scope_combo, "adaptive_scope_combo"),
        )
        adaptive_form.addRow(
            "GP length scale",
            _required(self.adaptive_length_scale_field, "adaptive_length_scale_field"),
        )
        adaptive_form.addRow(
            "proposal上限",
            _required(self.adaptive_proposal_limit_field, "adaptive_proposal_limit_field"),
        )
        adaptive.addLayout(adaptive_form)
        adaptive_build = _required(self.adaptive_build_button, "adaptive_build_button")
        set_primary_action(adaptive_build)
        adaptive.addWidget(adaptive_build)
        adaptive.addWidget(_required(self.adaptive_tree, "adaptive_tree"))
        adaptive_detail = _required(self.adaptive_detail_label, "adaptive_detail_label")
        adaptive_detail.setWordWrap(True)
        adaptive.addWidget(adaptive_detail)

        adaptive_extended_form = QFormLayout()
        adaptive_extended_form.addRow(
            "normalized GP length scale",
            _required(
                self.adaptive_extended_length_scale_field,
                "adaptive_extended_length_scale_field",
            ),
        )
        adaptive_extended_form.addRow(
            "Extended proposal上限",
            _required(
                self.adaptive_extended_proposal_limit_field,
                "adaptive_extended_proposal_limit_field",
            ),
        )
        adaptive.addLayout(adaptive_extended_form)
        adaptive_extended_build = _required(
            self.adaptive_extended_build_button,
            "adaptive_extended_build_button",
        )
        adaptive.addWidget(adaptive_extended_build)
        adaptive.addWidget(
            _required(self.adaptive_extended_tree, "adaptive_extended_tree")
        )
        adaptive_extended_detail = _required(
            self.adaptive_extended_detail_label,
            "adaptive_extended_detail_label",
        )
        adaptive_extended_detail.setWordWrap(True)
        adaptive.addWidget(adaptive_extended_detail)

        layout.addWidget(
            _advanced_block(
                "詳細: 次の測定候補",
                "O70 / O80Aの既存plannerを使います。Synthetic developmentは本番推薦を解放せず、"
                " Productionはcurrent campaign-backed eligible O60 evidenceを要求します。",
                adaptive_content,
            )
        )
        layout.addStretch(1)
        return _scroll_page(body)


def build_optimization_workspace_mount(
    repository: SceneRepository,
    document_id: str = F1_DOCUMENT_ID,
) -> WorkspaceMount:
    """Build the UX140 workspace through the shell's existing mount contract."""

    workspace = OptimizationWorkflowWorkspace(repository, document_id)

    def activate() -> None:
        refresh_legacy_editor_revision(workspace)
        workspace.refresh_from_authorities()

    return WorkspaceMount.from_widget(
        workspace,
        on_activate=activate,
        before_deactivate=lambda: legacy_editor_deactivation_guard(workspace),
        on_context_changed=workspace.select_section,
    )


__all__ = [
    "OPTIMIZATION_PAGE_IDS",
    "OptimizationWorkflowWorkspace",
    "build_optimization_workspace_mount",
    "normalize_optimization_page",
]
