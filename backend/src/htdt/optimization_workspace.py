from __future__ import annotations

from collections.abc import Callable
from threading import Event
from uuid import uuid4

import numpy as np
import pyvista as pv
from PySide6.QtCore import QObject, QSignalBlocker, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QListWidget,
    QListWidgetItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .analysis_markers import render_analysis_marker_cloud
from .cad_repository import SceneRepository, SceneRevision
from .cad_objectives import build_pareto_set
from .cad_objective_repository import CadObjectiveRepository
from .cad_scene import F1_DOCUMENT_ID
from .cad_search import (
    apply_candidate_positions,
    build_cad_search_spec,
    generate_cad_candidates,
    search_spec_current_working,
)
from .cad_search_models import CadCandidate, CadCandidateSetPage, CadSearchAxis, CadSearchSpec
from .cad_search_repository import CadSearchRepository
from .measurement_workspace import _MeasurementScrollArea
from .cad_measurement_repository import CadMeasurementRepository
from .cad_model_validation_repository import CadModelValidationRepository
from .cad_model_validation_service import CadModelValidationService
from .cad_roomsim_repository import CadRoomSimRepository
from .cad_measurement_loop import build_measurement_plan, complete_measurement_plan
from .cad_validation_campaign import (
    CadValidationCampaignCandidate,
    CadValidationCampaignRepeatability,
    CadValidationCampaignSensitivity,
    CadValidationCampaignSeparation,
    CadValidationTargetResponse,
    build_validation_campaign,
)
from .cad_validation_campaign_repository import CadValidationCampaignRepository
from .cad_validation_campaign_service import CadValidationCampaignService
from .native_editor import ROLE
from .prediction_workspace import PredictionWorkspaceWindow


def candidate_cloud_points(
    page: CadCandidateSetPage,
    primary_entity_id: str,
) -> np.ndarray:
    """Return one representative domain point per visible candidate."""

    points: list[tuple[float, float, float]] = []
    for candidate in page.candidates:
        position = candidate.positions.get(primary_entity_id)
        if position is None:
            continue
        points.append(
            (
                float(position['x_m']),
                float(position['y_m']),
                float(position['z_m']),
            )
        )
    if not points:
        return np.empty((0, 3), dtype=float)
    return np.asarray(points, dtype=float)


class _SearchTask(QObject):
    completed = Signal(object, object, object)

    def __init__(self, key: str, operation: Callable[[Event], object]) -> None:
        super().__init__()
        self.key = key
        self.operation = operation
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    @Slot()
    def run(self) -> None:
        if self.cancel_event.is_set():
            self.completed.emit(self.key, None, 'cancelled')
            return
        try:
            result = self.operation(self.cancel_event)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.completed.emit(self.key, None, 'cancelled')
            else:
                self.completed.emit(self.key, None, str(exc))
        else:
            if self.cancel_event.is_set():
                self.completed.emit(self.key, None, 'cancelled')
            else:
                self.completed.emit(self.key, result, None)


class OptimizationWorkspaceWindow(PredictionWorkspaceWindow):
    """N80a product layer: immutable SearchSpec, candidate preview and explicit apply."""

    search_page_limit = 250

    def __init__(self, repository: SceneRepository, document_id: str = F1_DOCUMENT_ID) -> None:
        self.search_repository = CadSearchRepository(repository)
        self.objective_repository = CadObjectiveRepository(repository, self.search_repository)
        self.measurement_repository = CadMeasurementRepository(repository)
        self.roomsim_repository = CadRoomSimRepository(repository, self.search_repository)
        self.validation_repository = CadModelValidationRepository(
            self.search_repository,
            self.roomsim_repository,
            self.measurement_repository,
            self.objective_repository,
        )
        self.validation_service = CadModelValidationService(
            self.search_repository,
            self.roomsim_repository,
            self.measurement_repository,
            self.objective_repository,
        )
        self.campaign_repository = CadValidationCampaignRepository(
            self.search_repository,
            self.measurement_repository,
        )
        self.campaign_service = CadValidationCampaignService(
            self.campaign_repository,
            self.roomsim_repository,
            self.measurement_repository,
            self.objective_repository,
            self.validation_service,
        )
        self.search_selected_spec_id: str | None = None
        self.search_selected_candidate_id: str | None = None
        self.search_preview_candidate_id: str | None = None
        self.search_candidate_page: CadCandidateSetPage | None = None
        self.search_binding_label: QLabel | None = None
        self.search_name_field: QLineEdit | None = None
        self.search_entity_combo: QComboBox | None = None
        self.search_axis_combo: QComboBox | None = None
        self.search_min_field: QDoubleSpinBox | None = None
        self.search_max_field: QDoubleSpinBox | None = None
        self.search_step_field: QDoubleSpinBox | None = None
        self.search_limit_field: QSpinBox | None = None
        self.search_axis_tree: QTreeWidget | None = None
        self.search_spec_tree: QTreeWidget | None = None
        self.search_candidate_tree: QTreeWidget | None = None
        self.search_summary_label: QLabel | None = None
        self.search_save_button: QPushButton | None = None
        self.search_generate_button: QPushButton | None = None
        self.search_cancel_button: QPushButton | None = None
        self.search_prev_button: QPushButton | None = None
        self.search_next_button: QPushButton | None = None
        self.search_preview_button: QPushButton | None = None
        self.search_clear_preview_button: QPushButton | None = None
        self.search_apply_button: QPushButton | None = None
        self.measurement_plan_button: QPushButton | None = None
        self.measurement_plan_label: QLabel | None = None
        self.measurement_plan_tree: QTreeWidget | None = None
        self.measurement_match_list: QListWidget | None = None
        self.measurement_complete_button: QPushButton | None = None
        self.objective_list: QListWidget | None = None
        self.pareto_tree: QTreeWidget | None = None
        self.pareto_summary_label: QLabel | None = None
        self.pareto_refresh_button: QPushButton | None = None
        self.validation_tree: QTreeWidget | None = None
        self.validation_detail_label: QLabel | None = None
        self.validation_refresh_button: QPushButton | None = None
        self.campaign_assignment_tree: QTreeWidget | None = None
        self.campaign_tree: QTreeWidget | None = None
        self.campaign_detail_label: QLabel | None = None
        self.campaign_model_version_field: QLineEdit | None = None
        self.campaign_low_field: QDoubleSpinBox | None = None
        self.campaign_high_field: QDoubleSpinBox | None = None
        self.campaign_residual_field: QDoubleSpinBox | None = None
        self.campaign_sensitivity_field: QDoubleSpinBox | None = None
        self.campaign_sensitivity_error_field: QDoubleSpinBox | None = None
        self.campaign_separation_field: QDoubleSpinBox | None = None
        self.campaign_assignments: dict[str, str] = {}
        self._search_actor_names: set[str] = set()
        self._search_tasks: dict[str, tuple[QThread, _SearchTask]] = {}
        self._search_task_spec_ids: dict[str, str] = {}
        self._current_search_task_id: str | None = None
        super().__init__(repository, document_id)
        self.setWindowTitle('Home Theater Digital Twin — 最適化CAD')
        self._create_search_dock()
        self._refresh_search_entities()
        self._refresh_search_specs()

    def _create_search_dock(self) -> None:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self.search_binding_label = QLabel('保存済みSceneRevisionから探索仕様を作成します')
        self.search_binding_label.setWordWrap(True)
        layout.addWidget(self.search_binding_label)

        semantics = QLabel(
            '候補はhard constraintを満たす幾何配置です。順位・推奨・音質評価ではありません。'
        )
        semantics.setWordWrap(True)
        layout.addWidget(semantics)

        form = QFormLayout()
        self.search_name_field = QLineEdit()
        self.search_name_field.setPlaceholderText('例: FL 前後 sweep')
        form.addRow('名前', self.search_name_field)

        self.search_entity_combo = QComboBox()
        self.search_entity_combo.setMinimumContentsLength(18)
        self.search_entity_combo.currentIndexChanged.connect(self._seed_search_axis_range)
        form.addRow('可動物体', self.search_entity_combo)

        self.search_axis_combo = QComboBox()
        self.search_axis_combo.addItem('X', 'x')
        self.search_axis_combo.addItem('Y', 'y')
        self.search_axis_combo.addItem('Z', 'z')
        self.search_axis_combo.currentIndexChanged.connect(self._seed_search_axis_range)
        form.addRow('軸', self.search_axis_combo)

        self.search_min_field = self._search_distance_field()
        self.search_max_field = self._search_distance_field()
        self.search_step_field = self._search_distance_field(minimum=0.001, value=0.10)
        form.addRow('最小', self.search_min_field)
        form.addRow('最大', self.search_max_field)
        form.addRow('刻み', self.search_step_field)

        self.search_limit_field = QSpinBox()
        self.search_limit_field.setRange(1, 50_000)
        self.search_limit_field.setValue(10_000)
        form.addRow('raw候補上限', self.search_limit_field)
        layout.addLayout(form)

        axis_actions = QHBoxLayout()
        add_axis = QPushButton('軸を追加 / 更新')
        add_axis.clicked.connect(self.add_search_axis)
        axis_actions.addWidget(add_axis)
        remove_axis = QPushButton('選択軸を削除')
        remove_axis.clicked.connect(self.remove_selected_search_axis)
        axis_actions.addWidget(remove_axis)
        layout.addLayout(axis_actions)

        self.search_axis_tree = QTreeWidget()
        self.search_axis_tree.setHeaderLabels(['物体', '軸', '最小', '最大', '刻み'])
        self.search_axis_tree.setMinimumHeight(120)
        layout.addWidget(self.search_axis_tree)

        self.search_save_button = QPushButton('探索仕様を保存')
        self.search_save_button.setToolTip(
            '現在の保存済みSceneRevisionとconstraint workspace hashへimmutable bindingします'
        )
        self.search_save_button.clicked.connect(self.save_search_spec)
        layout.addWidget(self.search_save_button)

        self.search_spec_tree = QTreeWidget()
        self.search_spec_tree.setHeaderLabels(['探索仕様', '入力版', '状態'])
        self.search_spec_tree.setMinimumHeight(150)
        self.search_spec_tree.itemSelectionChanged.connect(self._search_spec_selected)
        layout.addWidget(self.search_spec_tree)

        generation = QHBoxLayout()
        self.search_generate_button = QPushButton('候補を生成')
        self.search_generate_button.clicked.connect(self.generate_search_candidates_async)
        generation.addWidget(self.search_generate_button)
        self.search_cancel_button = QPushButton('生成をキャンセル')
        self.search_cancel_button.clicked.connect(self.cancel_search_generation)
        generation.addWidget(self.search_cancel_button)
        layout.addLayout(generation)

        paging = QHBoxLayout()
        self.search_prev_button = QPushButton('前の候補')
        self.search_prev_button.clicked.connect(self.previous_search_page)
        paging.addWidget(self.search_prev_button)
        self.search_next_button = QPushButton('次の候補')
        self.search_next_button.clicked.connect(self.next_search_page)
        paging.addWidget(self.search_next_button)
        layout.addLayout(paging)

        self.search_summary_label = QLabel('候補未生成')
        self.search_summary_label.setWordWrap(True)
        layout.addWidget(self.search_summary_label)

        self.search_candidate_tree = QTreeWidget()
        self.search_candidate_tree.setHeaderLabels(['候補', 'index', '位置'])
        self.search_candidate_tree.setMinimumHeight(180)
        self.search_candidate_tree.itemSelectionChanged.connect(self._search_candidate_selected)
        layout.addWidget(self.search_candidate_tree)

        candidate_actions = QHBoxLayout()
        self.search_preview_button = QPushButton('候補をpreview')
        self.search_preview_button.clicked.connect(self.preview_selected_candidate)
        candidate_actions.addWidget(self.search_preview_button)
        self.search_clear_preview_button = QPushButton('preview解除')
        self.search_clear_preview_button.clicked.connect(self.clear_candidate_preview)
        candidate_actions.addWidget(self.search_clear_preview_button)
        self.search_apply_button = QPushButton('候補を適用')
        self.search_apply_button.setToolTip('明示適用だけがSceneを変更し、1回のUndoで全位置を戻します')
        self.search_apply_button.clicked.connect(self.apply_selected_candidate)
        candidate_actions.addWidget(self.search_apply_button)
        layout.addLayout(candidate_actions)

        self.measurement_plan_button = QPushButton('現在の保存版を実測候補として記録')
        self.measurement_plan_button.setToolTip('候補適用後にSceneを保存してから、候補とその正確なSceneRevisionをimmutableに結びます')
        self.measurement_plan_button.clicked.connect(self.create_measurement_plan_for_selected_candidate)
        layout.addWidget(self.measurement_plan_button)
        self.measurement_plan_label = QLabel('実測候補未登録')
        self.measurement_plan_label.setWordWrap(True)
        layout.addWidget(self.measurement_plan_label)

        self.measurement_plan_tree = QTreeWidget()
        self.measurement_plan_tree.setHeaderLabels(['実測候補', '状態', 'Scene', '測定'])
        self.measurement_plan_tree.setMinimumHeight(120)
        self.measurement_plan_tree.itemSelectionChanged.connect(self._measurement_plan_selected)
        layout.addWidget(self.measurement_plan_tree)

        self.measurement_match_list = QListWidget()
        self.measurement_match_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.measurement_match_list.setMinimumHeight(90)
        layout.addWidget(self.measurement_match_list)

        self.measurement_complete_button = QPushButton('選択したN60実測を候補へ関連付け')
        self.measurement_complete_button.setToolTip(
            '候補適用時と完全一致するSceneRevision/content hashのmeasured evidenceだけを関連付けます'
        )
        self.measurement_complete_button.clicked.connect(self.complete_selected_measurement_plan)
        layout.addWidget(self.measurement_complete_button)

        comparison_label = QLabel('Pareto比較 · objectiveは独立指標のまま保持します')
        comparison_label.setWordWrap(True)
        layout.addWidget(comparison_label)

        self.objective_list = QListWidget()
        self.objective_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.objective_list.setMinimumHeight(100)
        layout.addWidget(self.objective_list)

        self.pareto_refresh_button = QPushButton('Pareto集合を再計算・保存')
        self.pareto_refresh_button.clicked.connect(self.refresh_pareto_comparison)
        layout.addWidget(self.pareto_refresh_button)

        self.pareto_summary_label = QLabel('objective evaluation未読込')
        self.pareto_summary_label.setWordWrap(True)
        layout.addWidget(self.pareto_summary_label)

        self.pareto_tree = QTreeWidget()
        self.pareto_tree.setHeaderLabels(['候補', 'Pareto', 'evidence', 'objective'])
        self.pareto_tree.setMinimumHeight(180)
        self.pareto_tree.itemSelectionChanged.connect(self._pareto_candidate_selected)
        layout.addWidget(self.pareto_tree)

        campaign_label = QLabel(
            '実室Validation Campaign · 測定前にcalibration/holdoutと閾値を固定'
        )
        campaign_label.setWordWrap(True)
        layout.addWidget(campaign_label)

        assignment_actions = QHBoxLayout()
        campaign_calibration = QPushButton('選択候補→calibration')
        campaign_calibration.clicked.connect(
            lambda: self.assign_selected_candidate_to_campaign('calibration')
        )
        assignment_actions.addWidget(campaign_calibration)
        campaign_holdout = QPushButton('選択候補→holdout')
        campaign_holdout.clicked.connect(
            lambda: self.assign_selected_candidate_to_campaign('holdout')
        )
        assignment_actions.addWidget(campaign_holdout)
        campaign_remove = QPushButton('campaignから外す')
        campaign_remove.clicked.connect(self.remove_selected_campaign_assignment)
        assignment_actions.addWidget(campaign_remove)
        layout.addLayout(assignment_actions)

        self.campaign_assignment_tree = QTreeWidget()
        self.campaign_assignment_tree.setHeaderLabels(['候補', '役割'])
        self.campaign_assignment_tree.setMinimumHeight(100)
        layout.addWidget(self.campaign_assignment_tree)

        campaign_form = QFormLayout()
        self.campaign_model_version_field = QLineEdit()
        self.campaign_model_version_field.setPlaceholderText('例: 5.40 Beta 135 API 0.9.8')
        campaign_form.addRow('model version', self.campaign_model_version_field)

        self.campaign_low_field = QDoubleSpinBox()
        self.campaign_low_field.setRange(1.0, 20000.0)
        self.campaign_low_field.setDecimals(1)
        self.campaign_low_field.setValue(20.0)
        campaign_form.addRow('検証帯域 low Hz', self.campaign_low_field)

        self.campaign_high_field = QDoubleSpinBox()
        self.campaign_high_field.setRange(1.0, 20000.0)
        self.campaign_high_field.setDecimals(1)
        self.campaign_high_field.setValue(160.0)
        campaign_form.addRow('検証帯域 high Hz', self.campaign_high_field)

        self.campaign_residual_field = QDoubleSpinBox()
        self.campaign_residual_field.setRange(0.0, 100.0)
        self.campaign_residual_field.setDecimals(2)
        self.campaign_residual_field.setValue(0.0)
        self.campaign_residual_field.setSpecialValueText('要設定')
        campaign_form.addRow('holdout RMS上限 dB', self.campaign_residual_field)

        self.campaign_sensitivity_field = QDoubleSpinBox()
        self.campaign_sensitivity_field.setRange(0.0, 1000.0)
        self.campaign_sensitivity_field.setDecimals(2)
        self.campaign_sensitivity_field.setValue(0.0)
        self.campaign_sensitivity_field.setSpecialValueText('要設定')
        campaign_form.addRow('感度上限 dB/m', self.campaign_sensitivity_field)

        self.campaign_sensitivity_error_field = QDoubleSpinBox()
        self.campaign_sensitivity_error_field.setRange(0.0, 1000.0)
        self.campaign_sensitivity_error_field.setDecimals(2)
        self.campaign_sensitivity_error_field.setValue(0.0)
        self.campaign_sensitivity_error_field.setSpecialValueText('要設定')
        campaign_form.addRow('感度誤差上限 dB/m', self.campaign_sensitivity_error_field)

        self.campaign_separation_field = QDoubleSpinBox()
        self.campaign_separation_field.setRange(0.0, 100.0)
        self.campaign_separation_field.setDecimals(2)
        self.campaign_separation_field.setValue(0.0)
        self.campaign_separation_field.setSpecialValueText('要設定')
        campaign_form.addRow('候補差 / repeatability', self.campaign_separation_field)
        layout.addLayout(campaign_form)

        campaign_save = QPushButton('Campaignを測定前にimmutable保存')
        campaign_save.setToolTip(
            'holdoutを実測結果から選び直せないよう、この時点の役割・target・閾値を固定します'
        )
        campaign_save.clicked.connect(self.save_validation_campaign)
        layout.addWidget(campaign_save)

        self.campaign_tree = QTreeWidget()
        self.campaign_tree.setHeaderLabels(['campaign', 'model', '候補', 'readiness'])
        self.campaign_tree.setMinimumHeight(130)
        self.campaign_tree.itemSelectionChanged.connect(self._campaign_selected)
        layout.addWidget(self.campaign_tree)

        campaign_actions = QHBoxLayout()
        campaign_refresh = QPushButton('readiness更新')
        campaign_refresh.clicked.connect(self.refresh_validation_campaigns)
        campaign_actions.addWidget(campaign_refresh)
        campaign_materialize = QPushButton('O30 objective evidence生成')
        campaign_materialize.clicked.connect(self.materialize_selected_campaign_objectives)
        campaign_actions.addWidget(campaign_materialize)
        campaign_rew_read = QPushButton('選択REW→Campaign実測')
        campaign_rew_read.setToolTip(
            '選択中のCampaign・planned Measurement Plan・現在SceneRevisionが一致する場合だけ、'
            'REW API測定をowned-room campaign evidenceとして読み込みます'
        )
        campaign_rew_read.clicked.connect(self.read_selected_rew_for_campaign_async)
        campaign_actions.addWidget(campaign_rew_read)
        layout.addLayout(campaign_actions)

        self.campaign_detail_label = QLabel('Campaign未選択')
        self.campaign_detail_label.setWordWrap(True)
        layout.addWidget(self.campaign_detail_label)

        validation_label = QLabel(
            'モデル検証 · residual / trend / sensitivity / repeatabilityを独立表示'
        )
        validation_label.setWordWrap(True)
        layout.addWidget(validation_label)

        self.validation_refresh_button = QPushButton('保存済みValidationRecordを更新')
        self.validation_refresh_button.clicked.connect(self.refresh_model_validations)
        layout.addWidget(self.validation_refresh_button)

        self.validation_tree = QTreeWidget()
        self.validation_tree.setHeaderLabels([
            'validation', 'scope', 'residual', 'trend', 'sensitivity', 'repeatability', 'gate'
        ])
        self.validation_tree.setMinimumHeight(150)
        self.validation_tree.itemSelectionChanged.connect(self._validation_selected)
        layout.addWidget(self.validation_tree)

        self.validation_detail_label = QLabel('ValidationRecord未選択')
        self.validation_detail_label.setWordWrap(True)
        layout.addWidget(self.validation_detail_label)
        layout.addStretch(1)

        dock = QDockWidget('最適化', self)
        scroll = _MeasurementScrollArea(panel, dock)
        dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._unify_right_context_docks(dock)
        dock.raise_()

    def assign_selected_candidate_to_campaign(self, split: str) -> None:
        candidate_id = self.search_selected_candidate_id
        if candidate_id is None:
            self.statusBar().showMessage('Campaignへ追加する候補を選択してください')
            return
        if split not in {'calibration', 'holdout'}:
            raise ValueError('campaign split must be calibration or holdout')
        self.campaign_assignments[candidate_id] = split
        self._refresh_campaign_assignment_tree()
        self.statusBar().showMessage(
            f'Campaign draft · {candidate_id[:12]} → {split}'
        )

    def remove_selected_campaign_assignment(self) -> None:
        tree = self.campaign_assignment_tree
        if tree is None:
            return
        item = tree.currentItem()
        candidate_id = None if item is None else item.data(0, ROLE)
        if not isinstance(candidate_id, str):
            return
        self.campaign_assignments.pop(candidate_id, None)
        self._refresh_campaign_assignment_tree()

    def _refresh_campaign_assignment_tree(self) -> None:
        tree = self.campaign_assignment_tree
        if tree is None:
            return
        tree.clear()
        for candidate_id, split in self.campaign_assignments.items():
            item = QTreeWidgetItem([candidate_id[:12], split])
            item.setData(0, ROLE, candidate_id)
            tree.addTopLevelItem(item)

    def save_validation_campaign(self) -> None:
        spec = self._selected_search_spec()
        page = self.search_candidate_page
        if spec is None or page is None:
            self.statusBar().showMessage(
                'SearchSpecを選択して候補集合を生成してからCampaignを保存してください'
            )
            return

        assignments = tuple(self.campaign_assignments.items())
        calibration = [candidate_id for candidate_id, split in assignments if split == 'calibration']
        holdout = [candidate_id for candidate_id, split in assignments if split == 'holdout']
        if len(calibration) < 1 or len(holdout) < 2:
            self.statusBar().showMessage(
                'Campaignには1件以上のcalibrationと2件以上のholdoutが必要です'
            )
            return

        model_version = (
            ''
            if self.campaign_model_version_field is None
            else self.campaign_model_version_field.text().strip()
        )
        low_hz = 20.0 if self.campaign_low_field is None else self.campaign_low_field.value()
        high_hz = 160.0 if self.campaign_high_field is None else self.campaign_high_field.value()
        max_residual = (
            0.0 if self.campaign_residual_field is None
            else self.campaign_residual_field.value()
        )
        max_sensitivity = (
            0.0 if self.campaign_sensitivity_field is None
            else self.campaign_sensitivity_field.value()
        )
        max_sensitivity_error = (
            0.0 if self.campaign_sensitivity_error_field is None
            else self.campaign_sensitivity_error_field.value()
        )
        separation_multiple = (
            0.0 if self.campaign_separation_field is None
            else self.campaign_separation_field.value()
        )
        if not model_version:
            self.statusBar().showMessage('Campaignのmodel versionを明示してください')
            return
        if high_hz <= low_hz:
            self.statusBar().showMessage('Campaignの検証帯域が不正です')
            return
        if min(max_residual, max_sensitivity, max_sensitivity_error, separation_multiple) <= 0:
            self.statusBar().showMessage('Campaignの検証閾値をすべて明示設定してください')
            return

        holdout_a, holdout_b = holdout[:2]
        try:
            campaign = build_validation_campaign(
                document_id=spec.document_id,
                search_spec_id=spec.search_spec_id,
                search_spec_sha256=spec.search_spec_sha256,
                candidate_set_sha256=page.candidate_set_sha256,
                model_id='rew-roomsim',
                model_version=model_version,
                requested_band_hz=(float(low_hz), float(high_hz)),
                max_holdout_rms_db=float(max_residual),
                candidates=tuple(
                    CadValidationCampaignCandidate(
                        candidate_id=candidate_id,
                        split=split,
                    )
                    for candidate_id, split in assignments
                ),
                objective_ids=('response.shape_rms_db',),
                target_response=CadValidationTargetResponse(
                    frequency_hz=(float(low_hz), float(high_hz)),
                    level_db=(0.0, 0.0),
                ),
                reference_band_hz=(float(low_hz), float(high_hz)),
                sensitivity=(
                    CadValidationCampaignSensitivity(
                        objective_id='response.shape_rms_db',
                        candidate_a_id=holdout_a,
                        candidate_b_id=holdout_b,
                        max_observed_sensitivity_per_m=float(max_sensitivity),
                        max_model_error_per_m=float(max_sensitivity_error),
                    ),
                ),
                repeatability=(
                    CadValidationCampaignRepeatability(
                        candidate_id=holdout_a,
                        min_measurements=2,
                    ),
                ),
                separation=(
                    CadValidationCampaignSeparation(
                        candidate_a_id=holdout_a,
                        candidate_b_id=holdout_b,
                        repeatability_candidate_id=holdout_a,
                        min_repeatability_multiple=float(separation_multiple),
                    ),
                ),
                required_applicability_codes=('geometry', 'band', 'routing'),
            )
            self.campaign_repository.save(campaign)
        except Exception as exc:
            self.statusBar().showMessage(f'Campaignを保存できません · {exc}')
            return

        self.campaign_assignments.clear()
        self._refresh_campaign_assignment_tree()
        self.refresh_validation_campaigns(select_campaign_id=campaign.campaign_id)
        self.statusBar().showMessage(
            f'Validation Campaignを事前登録しました · {campaign.campaign_id[:8]}'
        )

    def refresh_validation_campaigns(
        self,
        *,
        select_campaign_id: str | None = None,
    ) -> None:
        tree = self.campaign_tree
        if tree is None:
            return
        tree.clear()
        spec_id = self.search_selected_spec_id
        if spec_id is None:
            if self.campaign_detail_label is not None:
                self.campaign_detail_label.setText('Campaign未選択')
            return

        selected_item: QTreeWidgetItem | None = None
        try:
            campaigns = self.campaign_repository.list_for_search_spec(spec_id)
        except Exception as exc:
            self.statusBar().showMessage(f'Campaignを読めません · {exc}')
            return
        for campaign in campaigns:
            try:
                readiness = self.campaign_service.readiness(campaign.campaign_id)
                missing_count = sum(
                    len(candidate.missing_reasons)
                    for candidate in readiness.candidates
                ) + len(readiness.missing_reasons)
                readiness_text = 'ready' if readiness.evidence_ready else f'missing {missing_count}'
            except Exception as exc:
                readiness_text = f'error: {exc}'
            item = QTreeWidgetItem([
                campaign.campaign_id[:8],
                f'{campaign.model_id}/{campaign.model_version}',
                str(len(campaign.candidates)),
                readiness_text,
            ])
            item.setData(0, ROLE, campaign.campaign_id)
            tree.addTopLevelItem(item)
            if campaign.campaign_id == select_campaign_id:
                selected_item = item
        if selected_item is None and tree.topLevelItemCount() > 0:
            selected_item = tree.topLevelItem(tree.topLevelItemCount() - 1)
        if selected_item is not None:
            tree.setCurrentItem(selected_item)
        else:
            self._campaign_selected()

    def _selected_campaign(self):
        tree = self.campaign_tree
        if tree is None:
            return None
        item = tree.currentItem()
        campaign_id = None if item is None else item.data(0, ROLE)
        if not isinstance(campaign_id, str):
            return None
        return self.campaign_repository.get(campaign_id)

    def _campaign_selected(self) -> None:
        campaign = self._selected_campaign()
        label = self.campaign_detail_label
        if label is None:
            return
        if campaign is None:
            label.setText('Campaign未選択')
            return
        try:
            readiness = self.campaign_service.readiness(campaign.campaign_id)
        except Exception as exc:
            label.setText(f'Campaign readinessを読めません · {exc}')
            return
        lines = [
            f'campaign {campaign.campaign_id[:8]} · SHA {campaign.campaign_sha256[:8]}',
            f'{campaign.model_id} / {campaign.model_version}',
            f'band {campaign.requested_band_hz[0]:g}–{campaign.requested_band_hz[1]:g} Hz · '
            f'objective {", ".join(campaign.objective_ids)}',
            f'preregistered {campaign.created_at_utc}',
        ]
        for candidate in readiness.candidates:
            state = 'ready' if not candidate.missing_reasons else 'missing'
            lines.append(
                f'{candidate.candidate_id[:12]} · {candidate.split} · {state} · '
                f'measurements {len(candidate.measurement_ids)}'
            )
            lines.extend(
                f'  - {reason}'
                for reason in candidate.missing_reasons
            )
        lines.extend(f'stop: {reason}' for reason in readiness.missing_reasons)
        lines.append(
            'evidence ready' if readiness.evidence_ready else 'evidence不足 · O70はdisabled'
        )
        label.setText('\n'.join(lines))

    def materialize_selected_campaign_objectives(self) -> None:
        campaign = self._selected_campaign()
        if campaign is None:
            self.statusBar().showMessage('Campaignを選択してください')
            return
        try:
            evaluation_ids = self.campaign_service.materialize_objective_evidence(
                campaign.campaign_id
            )
        except Exception as exc:
            self.statusBar().showMessage(f'objective evidenceを生成できません · {exc}')
            self._campaign_selected()
            return
        self.refresh_validation_campaigns(select_campaign_id=campaign.campaign_id)
        self.statusBar().showMessage(
            f'O30 objective evidenceを確認/保存しました · {len(evaluation_ids)}件'
        )


    def read_selected_rew_for_campaign_async(self) -> None:
        campaign = self._selected_campaign()
        plan = self._selected_measurement_plan()
        if campaign is None:
            self.statusBar().showMessage('Campaignを選択してください')
            return
        if plan is None:
            self.statusBar().showMessage('Campaign候補のMeasurement Planを選択してください')
            return
        if plan.status != 'planned':
            self.statusBar().showMessage('REW読込にはplanned状態のMeasurement Planが必要です')
            return
        if (
            plan.search_spec_id != campaign.search_spec_id
            or plan.search_spec_sha256 != campaign.search_spec_sha256
            or plan.candidate_set_sha256 != campaign.candidate_set_sha256
        ):
            self.statusBar().showMessage('Measurement PlanとCampaignの探索authorityが一致しません')
            return
        if not any(
            assignment.candidate_id == plan.candidate_id
            for assignment in campaign.candidates
        ):
            self.statusBar().showMessage('Measurement Plan候補は選択Campaignに含まれていません')
            return
        if (
            self.working is None
            or self.working.is_dirty
            or self.working.source_revision_id != plan.applied_scene_revision_id
        ):
            self.statusBar().showMessage(
                '現在SceneをMeasurement Planのapplied revisionへ戻し、未保存編集を無くしてください'
            )
            return

        try:
            self._start_selected_rew_read(
                validation_scope='owned_room',
                validation_campaign_id=campaign.campaign_id,
                evidence_type_override='measured',
            )
        except Exception as exc:
            self.statusBar().showMessage(f'Campaign REW読込を開始できません · {exc}')
            return

    def create_measurement_plan_for_selected_candidate(self) -> None:
        if self.search_selected_spec_id is None or self.search_selected_candidate_id is None:
            self.statusBar().showMessage('探索仕様と候補を選択してください')
            return
        latest = self.repository.latest(self.document_id)
        if latest is None or self.working is None or self.working.is_dirty:
            self.statusBar().showMessage('候補適用後のSceneを保存してから実測候補を記録してください')
            return
        try:
            plan = build_measurement_plan(
                self.repository, self.search_repository,
                search_spec_id=self.search_selected_spec_id,
                candidate_id=self.search_selected_candidate_id,
                applied_scene_revision_id=latest.revision_id,
            )
            self.measurement_repository.save_measurement_plan(plan)
        except Exception as exc:
            self.statusBar().showMessage(f'実測候補を記録できません · {exc}')
            return
        if self.measurement_plan_label is not None:
            self.measurement_plan_label.setText(
                f'planned · {plan.candidate_id[:12]} · Scene {plan.applied_scene_revision_id[:8]}'
            )
        self.refresh_measurement_plans()
        self.statusBar().showMessage('実測候補をimmutable保存しました · 実際の配置変更と測定は人が行います')

    def refresh_measurement_plans(self) -> None:
        tree = self.measurement_plan_tree
        if tree is None:
            return
        tree.clear()
        spec_id = self.search_selected_spec_id
        if spec_id is None:
            if self.measurement_match_list is not None:
                self.measurement_match_list.clear()
            return
        plans = self.measurement_repository.latest_measurement_plans(spec_id)
        for plan in plans:
            item = QTreeWidgetItem([
                plan.candidate_id[:12],
                plan.status,
                plan.applied_scene_revision_id[:8],
                str(len(plan.measurement_ids)),
            ])
            item.setData(0, ROLE, plan.plan_id)
            tree.addTopLevelItem(item)
        if self.measurement_plan_label is not None:
            planned = sum(plan.status == 'planned' for plan in plans)
            measured = sum(plan.status == 'measured' for plan in plans)
            self.measurement_plan_label.setText(
                f'実測キュー {len(plans)} · planned {planned} · measured {measured}'
            )

    def _selected_measurement_plan(self):
        tree = self.measurement_plan_tree
        spec_id = self.search_selected_spec_id
        if tree is None or spec_id is None:
            return None
        item = tree.currentItem()
        if item is None:
            return None
        plan_id = item.data(0, ROLE)
        if not isinstance(plan_id, str):
            return None
        return next(
            (plan for plan in self.measurement_repository.latest_measurement_plans(spec_id)
             if plan.plan_id == plan_id),
            None,
        )

    def _measurement_plan_selected(self) -> None:
        plan = self._selected_measurement_plan()
        matches = self.measurement_match_list
        if matches is None:
            return
        matches.clear()
        if plan is None:
            if self.measurement_complete_button is not None:
                self.measurement_complete_button.setEnabled(False)
            return
        records = self.measurement_repository.list_measurements(plan.document_id)
        for record in records:
            if (
                record.scene_revision_id != plan.applied_scene_revision_id
                or record.scene_content_hash != plan.applied_scene_content_hash
                or record.evidence_type != 'measured'
            ):
                continue
            item = QListWidgetItem(
                f'{record.measurement_id[:12]} · {record.channel_role} · {record.source_kind}'
            )
            item.setData(Qt.ItemDataRole.UserRole, record.measurement_id)
            matches.addItem(item)
            if record.measurement_id in plan.measurement_ids:
                item.setSelected(True)
        if self.measurement_complete_button is not None:
            self.measurement_complete_button.setEnabled(plan.status == 'planned' and matches.count() > 0)

    def complete_selected_measurement_plan(self) -> None:
        plan = self._selected_measurement_plan()
        matches = self.measurement_match_list
        if plan is None or matches is None:
            return
        measurement_ids = tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in matches.selectedItems()
        )
        if not measurement_ids:
            self.statusBar().showMessage('関連付けるN60実測を選択してください')
            return
        try:
            completed = complete_measurement_plan(
                plan,
                self.measurement_repository,
                measurement_ids,
            )
            self.measurement_repository.save_measurement_plan(completed)
        except Exception as exc:
            self.statusBar().showMessage(f'実測を関連付けできません · {exc}')
            return
        self.refresh_measurement_plans()
        self.refresh_validation_campaigns()
        self.statusBar().showMessage(
            f'実測候補をcompletedにしました · measured evidence {len(completed.measurement_ids)}件'
        )

    @staticmethod
    def _validation_gate_summary(checks) -> str:
        if not checks:
            return '—'
        passed = sum(getattr(check, 'gate', None) == 'pass' for check in checks)
        failed = sum(getattr(check, 'gate', None) == 'fail' for check in checks)
        insufficient = sum(getattr(check, 'gate', None) == 'insufficient' for check in checks)
        parts = [f'pass {passed}']
        if failed:
            parts.append(f'fail {failed}')
        if insufficient:
            parts.append(f'insufficient {insufficient}')
        return ' / '.join(parts)

    def refresh_model_validations(self) -> None:
        tree = self.validation_tree
        if tree is None:
            return
        tree.clear()
        if self.validation_detail_label is not None:
            self.validation_detail_label.setText('ValidationRecord未選択')
        spec_id = self.search_selected_spec_id
        if spec_id is None:
            return
        try:
            records = self.validation_repository.list_for_search_spec(spec_id)
        except Exception as exc:
            self.statusBar().showMessage(f'ValidationRecordを読めません · {exc}')
            return
        for record in records:
            repeatability = '—'
            if record.repeatability_checks:
                floors = ', '.join(
                    f'{check.rms_floor_db:.3g} dB'
                    for check in record.repeatability_checks
                )
                repeatability = f'{len(record.repeatability_checks)} group · {floors}'
            item = QTreeWidgetItem([
                record.validation_id[:8],
                record.evidence_scope,
                record.residual_gate,
                self._validation_gate_summary(record.trend_checks),
                self._validation_gate_summary(record.sensitivity_checks),
                repeatability,
                record.recommendation_gate,
            ])
            item.setData(0, ROLE, record.validation_id)
            tree.addTopLevelItem(item)

    def _validation_selected(self) -> None:
        tree = self.validation_tree
        label = self.validation_detail_label
        if tree is None or label is None:
            return
        item = tree.currentItem()
        validation_id = None if item is None else item.data(0, ROLE)
        if not isinstance(validation_id, str):
            label.setText('ValidationRecord未選択')
            return
        record = self.validation_repository.get(validation_id)
        if record is None:
            label.setText('ValidationRecordが見つかりません')
            return

        calibration_count = sum(pair.split == 'calibration' for pair in record.pairs)
        holdout_count = sum(pair.split == 'holdout' for pair in record.pairs)
        lines = [
            f'model {record.model_id} / {record.model_version}',
            f'calibration {calibration_count} · holdout {holdout_count} · '
            f'band {record.requested_band_hz[0]:g}–{record.requested_band_hz[1]:g} Hz',
            f'residual {record.residual_gate} · holdout RMS '
            f'{record.holdout_rms_db if record.holdout_rms_db is not None else "—"} dB',
        ]
        for check in record.trend_checks:
            agreement = '—' if check.agreement_ratio is None else f'{check.agreement_ratio:.3f}'
            lines.append(
                f'trend {check.objective_id}: {check.gate} · agreement {agreement} · '
                f'comparable {check.comparable_pairs}'
            )
        for check in record.sensitivity_checks:
            lines.append(
                f'sensitivity {check.objective_id} {check.candidate_a_id[:8]}/{check.candidate_b_id[:8]}: '
                f'{check.gate} · observed {check.observed_sensitivity_per_m:.3g} '
                f'{check.unit}/m · model error {check.model_error_per_m:.3g} {check.unit}/m'
            )
        for check in record.repeatability_checks:
            lines.append(
                f'repeatability Scene {check.scene_revision_id[:8]}: '
                f'{check.rms_floor_db:.3g} dB · {len(check.measurement_ids)} repeats'
            )
        for check in record.separation_checks:
            ratio = '∞' if check.separation_ratio is None and check.response_difference_rms_db > 0 else (
                '—' if check.separation_ratio is None else f'{check.separation_ratio:.3g}×'
            )
            lines.append(
                f'separation {check.candidate_a_id[:8]}/{check.candidate_b_id[:8]}: '
                f'{check.gate} · {ratio} repeatability'
            )
        for check in record.applicability_checks:
            lines.append(
                f'applicability {check.code}: {"pass" if check.passed else "fail"} · {check.detail}'
            )
        lines.append(f'recommendation {record.recommendation_gate}')
        if record.gate_reasons:
            lines.extend(f'stop: {reason}' for reason in record.gate_reasons)
        label.setText('\n'.join(lines))

    def refresh_pareto_comparison(self) -> None:
        spec_id = self.search_selected_spec_id
        if spec_id is None or self.objective_list is None or self.pareto_tree is None:
            return
        spec = self.search_repository.get(spec_id)
        if (
            spec is None
            or self.working is None
            or not search_spec_current_working(
                spec,
                self.working,
                self.constraint_set,
                current_document_id=self.document_id,
            )
        ):
            self.pareto_tree.clear()
            if self.pareto_summary_label is not None:
                self.pareto_summary_label.setText('staleなSearchSpecではPareto集合を更新できません')
            self.statusBar().showMessage('Pareto比較を拒否しました · SearchSpec/Scene/constraint authorityがstaleです')
            return

        evaluations = self.objective_repository.latest_evaluations_by_candidate(spec_id)
        if not evaluations:
            self.objective_list.clear()
            self.pareto_tree.clear()
            if self.pareto_summary_label is not None:
                self.pareto_summary_label.setText('この探索仕様にはobjective evaluationがありません')
            return

        available = tuple(metric.objective_id for metric in evaluations[0].vector.metrics)
        expected_ids = set(available)
        expected_units = {metric.objective_id: metric.unit for metric in evaluations[0].vector.metrics}
        for evaluation in evaluations[1:]:
            metric_map = {metric.objective_id: metric for metric in evaluation.vector.metrics}
            if set(metric_map) != expected_ids:
                self.pareto_tree.clear()
                self.pareto_summary_label.setText('objective集合が候補間で一致しません · Pareto比較を中止')
                self.statusBar().showMessage('Pareto比較を拒否しました · objective集合不一致')
                return
            if any(metric_map[objective_id].unit != expected_units[objective_id] for objective_id in available):
                self.pareto_tree.clear()
                self.pareto_summary_label.setText('objective単位が候補間で一致しません · Pareto比較を中止')
                self.statusBar().showMessage('Pareto比較を拒否しました · objective単位不一致')
                return

        previous = {item.data(Qt.ItemDataRole.UserRole) for item in self.objective_list.selectedItems()}
        self.objective_list.clear()
        for objective_id in available:
            item = QListWidgetItem(objective_id)
            item.setData(Qt.ItemDataRole.UserRole, objective_id)
            self.objective_list.addItem(item)
            if not previous or objective_id in previous:
                item.setSelected(True)
        selected = tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.objective_list.selectedItems()
        )
        if not selected:
            selected = available

        try:
            built = build_pareto_set(evaluations, selected)
            existing = self.objective_repository.find_pareto_set_by_sha(
                spec_id, built.pareto_sha256
            )
            pareto_set = existing or built
            if existing is None:
                self.objective_repository.save_pareto_set(pareto_set)
        except Exception as exc:
            self.pareto_tree.clear()
            if self.pareto_summary_label is not None:
                self.pareto_summary_label.setText(f'Pareto比較を作成できません · {exc}')
            self.statusBar().showMessage(f'Pareto比較を拒否しました · {exc}')
            return

        non_dominated = set(pareto_set.result.non_dominated_candidate_ids)
        self.pareto_tree.clear()
        for evaluation in evaluations:
            metric_map = {metric.objective_id: metric for metric in evaluation.vector.metrics}
            provenance = ', '.join(
                f'{ref.evidence_class}:{ref.source_kind}:{ref.source_id[:12]}'
                for ref in evaluation.input_refs
            )
            values = '; '.join(
                f'{objective_id}={metric_map[objective_id].value:.4g} {metric_map[objective_id].unit}'
                for objective_id in selected
            )
            item = QTreeWidgetItem([
                evaluation.candidate_id[:12],
                '非劣' if evaluation.candidate_id in non_dominated else '支配あり',
                provenance,
                values,
            ])
            item.setData(0, ROLE, evaluation.candidate_id)
            self.pareto_tree.addTopLevelItem(item)
        if self.pareto_summary_label is not None:
            reused = ' · 既存snapshot' if existing is not None else ''
            self.pareto_summary_label.setText(
                f'{len(evaluations)}候補 · 非劣 {len(non_dominated)} · '
                f'objective {len(selected)} · {pareto_set.pareto_set_id[:8]}{reused}'
            )

    def _pareto_candidate_selected(self) -> None:
        if self.pareto_tree is None or self.search_candidate_tree is None:
            return
        item = self.pareto_tree.currentItem()
        if item is None:
            return
        candidate_id = item.data(0, ROLE)
        if not isinstance(candidate_id, str):
            return
        self.search_selected_candidate_id = candidate_id
        found = False
        for index in range(self.search_candidate_tree.topLevelItemCount()):
            candidate_item = self.search_candidate_tree.topLevelItem(index)
            payload = candidate_item.data(0, ROLE)
            if isinstance(payload, dict) and payload.get('candidate_id') == candidate_id:
                self.search_candidate_tree.setCurrentItem(candidate_item)
                found = True
                break
        if not found:
            self.statusBar().showMessage(
                'Pareto候補は現在のcandidate page外です · candidate pageを移動してからpreview/applyしてください'
            )

    @staticmethod
    def _search_distance_field(*, minimum: float = -1000.0, value: float = 0.0) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(minimum, 1000.0)
        field.setDecimals(3)
        field.setSingleStep(0.05)
        field.setValue(value)
        field.setSuffix(' m')
        return field

    def _refresh_search_entities(self) -> None:
        combo = self.search_entity_combo
        if combo is None or self.working is None:
            return
        previous = combo.currentData()
        with QSignalBlocker(combo):
            combo.clear()
            for entity in self.working.committed_document.entities:
                combo.addItem(f'{entity.name} · {entity.kind}', entity.entity_id)
            if previous is not None:
                index = combo.findData(previous)
                if index >= 0:
                    combo.setCurrentIndex(index)
        self._seed_search_axis_range()

    def _seed_search_axis_range(self) -> None:
        if (
            self.working is None
            or self.search_entity_combo is None
            or self.search_axis_combo is None
            or self.search_min_field is None
            or self.search_max_field is None
        ):
            return
        entity_id = self.search_entity_combo.currentData()
        axis = self.search_axis_combo.currentData()
        if entity_id is None or axis not in ('x', 'y', 'z'):
            return
        try:
            entity = self.working.committed_document.entity(str(entity_id))
        except KeyError:
            return
        position = float(getattr(entity.position, f'{axis}_m'))
        room = self.working.committed_document.room
        upper = None
        if room is not None:
            upper = {'x': float(room.width_m), 'y': float(room.depth_m), 'z': float(room.height_m)}[axis]
        low = max(0.0, position - 0.50) if upper is not None else position - 0.50
        high = min(upper, position + 0.50) if upper is not None else position + 0.50
        self.search_min_field.setValue(low)
        self.search_max_field.setValue(max(low, high))

    def add_search_axis(self) -> None:
        if (
            self.search_axis_tree is None
            or self.search_entity_combo is None
            or self.search_axis_combo is None
            or self.search_min_field is None
            or self.search_max_field is None
            or self.search_step_field is None
        ):
            return
        entity_id = self.search_entity_combo.currentData()
        axis = self.search_axis_combo.currentData()
        if entity_id is None or axis not in ('x', 'y', 'z'):
            return
        try:
            item = CadSearchAxis(
                entity_id=str(entity_id),
                axis=axis,
                min_m=float(self.search_min_field.value()),
                max_m=float(self.search_max_field.value()),
                step_m=float(self.search_step_field.value()),
            )
        except Exception as exc:
            self.statusBar().showMessage(f'探索軸を追加できません · {exc}')
            return

        for index in range(self.search_axis_tree.topLevelItemCount()):
            current = self.search_axis_tree.topLevelItem(index)
            payload = current.data(0, ROLE)
            if isinstance(payload, dict) and (
                payload.get('entity_id'), payload.get('axis')
            ) == (item.entity_id, item.axis):
                self._set_axis_tree_item(current, item)
                return
        tree_item = QTreeWidgetItem()
        self._set_axis_tree_item(tree_item, item)
        self.search_axis_tree.addTopLevelItem(tree_item)

    @staticmethod
    def _set_axis_tree_item(tree_item: QTreeWidgetItem, axis: CadSearchAxis) -> None:
        tree_item.setText(0, axis.entity_id)
        tree_item.setText(1, axis.axis.upper())
        tree_item.setText(2, f'{axis.min_m:.3f}')
        tree_item.setText(3, f'{axis.max_m:.3f}')
        tree_item.setText(4, f'{axis.step_m:.3f}')
        tree_item.setData(0, ROLE, axis.model_dump(mode='json'))

    def remove_selected_search_axis(self) -> None:
        tree = self.search_axis_tree
        if tree is None:
            return
        item = tree.currentItem()
        if item is None:
            return
        index = tree.indexOfTopLevelItem(item)
        if index >= 0:
            tree.takeTopLevelItem(index)

    def _draft_search_axes(self) -> tuple[CadSearchAxis, ...]:
        tree = self.search_axis_tree
        if tree is None:
            return ()
        result: list[CadSearchAxis] = []
        for index in range(tree.topLevelItemCount()):
            payload = tree.topLevelItem(index).data(0, ROLE)
            if isinstance(payload, dict):
                result.append(CadSearchAxis.model_validate(payload))
        return tuple(result)

    def _saved_search_revision(self) -> SceneRevision:
        if self.working is None or self.working.source_revision_id is None:
            raise ValueError('保存済みSceneRevisionが必要です')
        if self.working.has_preview:
            raise ValueError('編集中のtransformを完了またはキャンセルしてください')
        if self.working.is_dirty:
            raise ValueError('探索仕様を作る前に現在の配置を保存してください')
        revision = self.repository.get(self.working.source_revision_id)
        if revision is None:
            raise ValueError('現在のSceneRevisionを読み込めません')
        return revision

    def save_search_spec(self) -> None:
        axes = self._draft_search_axes()
        if not axes:
            self.statusBar().showMessage('探索仕様には少なくとも1つの可動軸が必要です')
            return
        try:
            revision = self._saved_search_revision()
            limit = 10_000 if self.search_limit_field is None else int(self.search_limit_field.value())
            name = None if self.search_name_field is None else self.search_name_field.text()
            spec, estimate = build_cad_search_spec(
                revision,
                self.constraint_set,
                axes,
                candidate_limit=limit,
                name=name,
            )
            self.search_repository.save(spec)
        except Exception as exc:
            self.statusBar().showMessage(f'探索仕様を保存できません · {exc}')
            return

        self.search_selected_spec_id = spec.search_spec_id
        self.search_candidate_page = None
        self.search_selected_candidate_id = None
        self.search_preview_candidate_id = None
        self._refresh_search_specs()
        self._remove_search_overlays()
        self.statusBar().showMessage(
            f'探索仕様を保存しました · raw候補 {estimate["raw_candidate_count"]} · '
            f'revision {spec.scene_revision_id[:8]}'
        )

    def _refresh_search_specs(self) -> None:
        tree = self.search_spec_tree
        if tree is None:
            return
        specs = self.search_repository.list_specs(self.document_id)
        if specs and self.search_selected_spec_id is None:
            self.search_selected_spec_id = specs[-1].search_spec_id

        selected_item: QTreeWidgetItem | None = None
        with QSignalBlocker(tree):
            tree.clear()
            for spec in reversed(specs):
                current = (
                    self.working is not None
                    and search_spec_current_working(
                    spec,
                    self.working,
                    self.constraint_set,
                    current_document_id=self.document_id,
                )
                )
                item = QTreeWidgetItem(
                    [
                        spec.name or '探索仕様',
                        spec.scene_revision_id[:8],
                        'current' if current else 'stale',
                    ]
                )
                item.setData(0, ROLE, spec.search_spec_id)
                tree.addTopLevelItem(item)
                if spec.search_spec_id == self.search_selected_spec_id:
                    selected_item = item
            if selected_item is not None:
                tree.setCurrentItem(selected_item)
        self._refresh_search_binding_state()

    def _search_spec_selected(self) -> None:
        tree = self.search_spec_tree
        if tree is None:
            return
        item = tree.currentItem()
        spec_id = None if item is None else item.data(0, ROLE)
        normalized = None if spec_id is None else str(spec_id)
        if normalized != self.search_selected_spec_id:
            self.search_candidate_page = None
            self.search_selected_candidate_id = None
            self.search_preview_candidate_id = None
            self.campaign_assignments.clear()
            self._refresh_campaign_assignment_tree()
        self.search_selected_spec_id = normalized
        self._refresh_search_binding_state()
        self._refresh_search_candidate_tree()
        self.refresh_measurement_plans()
        self.refresh_validation_campaigns()
        self.refresh_model_validations()
        self._render_search_overlay()

    def _selected_search_spec(self) -> CadSearchSpec | None:
        if self.search_selected_spec_id is None:
            return None
        return self.search_repository.get(self.search_selected_spec_id)

    def _selected_search_candidate(self) -> CadCandidate | None:
        page = self.search_candidate_page
        if page is None or self.search_selected_candidate_id is None:
            return None
        return next(
            (
                candidate
                for candidate in page.candidates
                if candidate.candidate_id == self.search_selected_candidate_id
            ),
            None,
        )

    def _refresh_search_binding_state(self) -> None:
        spec = self._selected_search_spec()
        current = (
            spec is not None
            and self.working is not None
            and search_spec_current_working(
                    spec,
                    self.working,
                    self.constraint_set,
                    current_document_id=self.document_id,
                )
        )
        if self.search_binding_label is not None:
            if self.working is None or self.working.source_revision_id is None:
                self.search_binding_label.setText('保存済みSceneRevisionがありません')
            elif spec is None:
                self.search_binding_label.setText(
                    f'現在のrevision {self.working.source_revision_id[:8]} · 探索仕様を作成してください'
                )
            else:
                state = 'current' if current else 'stale'
                self.search_binding_label.setText(
                    f'SearchSpec {spec.search_spec_id[:8]} · source {spec.scene_revision_id[:8]} · {state}'
                )
        busy = self._current_search_task_id is not None
        if self.search_save_button is not None:
            self.search_save_button.setEnabled(
                not busy
                and self.working is not None
                and self.working.source_revision_id is not None
                and not self.working.is_dirty
                and not self.working.has_preview
            )
        if self.search_generate_button is not None:
            self.search_generate_button.setEnabled(not busy and bool(current))
        if self.search_cancel_button is not None:
            self.search_cancel_button.setEnabled(busy)
        has_candidate = self._selected_search_candidate() is not None and bool(current)
        if self.search_preview_button is not None:
            self.search_preview_button.setEnabled(has_candidate)
        if self.search_apply_button is not None:
            self.search_apply_button.setEnabled(has_candidate)
        if self.search_clear_preview_button is not None:
            self.search_clear_preview_button.setEnabled(self.search_preview_candidate_id is not None)
        page = self.search_candidate_page
        if self.search_prev_button is not None:
            self.search_prev_button.setEnabled(
                not busy and bool(current) and page is not None and page.offset > 0
            )
        if self.search_next_button is not None:
            self.search_next_button.setEnabled(
                not busy
                and bool(current)
                and page is not None
                and page.offset + len(page.candidates) < page.feasible_candidate_count
            )

    def generate_search_candidates_async(self, *, offset: int | None = None) -> None:
        if self._current_search_task_id is not None:
            return
        spec = self._selected_search_spec()
        if spec is None or self.working is None:
            self.statusBar().showMessage('生成する探索仕様を選択してください')
            return
        if not search_spec_current_working(
            spec,
            self.working,
            self.constraint_set,
            current_document_id=self.document_id,
        ):
            self.statusBar().showMessage('staleな探索仕様から現在sceneへ候補を生成できません')
            self._refresh_search_binding_state()
            return

        page_offset = 0 if offset is None else max(0, int(offset))
        key = str(uuid4())
        self._current_search_task_id = key
        self._search_task_spec_ids[key] = spec.search_spec_id
        self._refresh_search_binding_state()
        self.statusBar().showMessage(
            f'候補生成中… SearchSpec {spec.search_spec_id[:8]} · offset {page_offset}'
        )
        self._start_search_task(
            key,
            lambda cancel_event: generate_cad_candidates(
                self.repository,
                spec,
                offset=page_offset,
                limit=self.search_page_limit,
                cancelled=cancel_event.is_set,
            ),
        )

    def _start_search_task(self, key: str, operation: Callable[[Event], object]) -> None:
        thread = QThread(self)
        worker = _SearchTask(key, operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._search_task_completed)
        worker.completed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._search_tasks[key] = (thread, worker)
        thread.start()

    def cancel_search_generation(self) -> None:
        key = self._current_search_task_id
        if key is None:
            return
        record = self._search_tasks.get(key)
        if record is not None:
            record[1].cancel()
        self.statusBar().showMessage('候補生成をキャンセルしています…')

    @Slot(object, object, object)
    def _search_task_completed(self, key: object, result: object, error: object) -> None:
        task_id = str(key)
        spec_id = self._search_task_spec_ids.pop(task_id, None)
        self._search_tasks.pop(task_id, None)
        if self._current_search_task_id == task_id:
            self._current_search_task_id = None

        if error == 'cancelled':
            self.statusBar().showMessage('候補生成をキャンセルしました')
            self._refresh_search_binding_state()
            return
        if error is not None:
            self.statusBar().showMessage(f'候補生成に失敗しました · {error}')
            self._refresh_search_binding_state()
            return
        if not isinstance(result, CadCandidateSetPage):
            self.statusBar().showMessage('候補生成結果を拒否しました · result contract mismatch')
            self._refresh_search_binding_state()
            return
        spec = None if spec_id is None else self.search_repository.get(spec_id)
        if (
            spec is None
            or self.working is None
            or not search_spec_current_working(
                        spec,
                        self.working,
                        self.constraint_set,
                        current_document_id=self.document_id,
                    )
        ):
            self.statusBar().showMessage('古い候補生成結果を破棄しました · scene/constraintが変更されています')
            self._refresh_search_binding_state()
            return
        if spec.search_spec_id != self.search_selected_spec_id:
            self.statusBar().showMessage('候補生成は完了しました · 別の探索仕様が選択されています')
            self._refresh_search_binding_state()
            return

        self.search_candidate_page = result
        self.search_preview_candidate_id = None
        self.search_selected_candidate_id = (
            result.candidates[0].candidate_id if result.candidates else None
        )
        self._refresh_search_candidate_tree()
        self._refresh_search_binding_state()
        self._render_search_overlay()
        if self.search_summary_label is not None:
            self.search_summary_label.setText(
                f'raw {result.raw_candidate_count} · feasible {result.feasible_candidate_count} · '
                f'rejected {result.rejected_candidate_count} · duplicate {result.duplicate_candidate_count} · '
                f'表示 {result.offset + 1 if result.candidates else 0}–'
                f'{result.offset + len(result.candidates)}'
            )
        self.statusBar().showMessage(
            f'候補を生成しました · feasible {result.feasible_candidate_count} · '
            f'set {result.candidate_set_sha256[:8]}'
        )

    def _refresh_search_candidate_tree(self) -> None:
        tree = self.search_candidate_tree
        if tree is None:
            return
        page = self.search_candidate_page
        selected_item: QTreeWidgetItem | None = None
        with QSignalBlocker(tree):
            tree.clear()
            if page is None:
                return
            for candidate in page.candidates:
                position_text = ' · '.join(
                    f'{entity_id}:({position["x_m"]:.2f},{position["y_m"]:.2f},{position["z_m"]:.2f})'
                    for entity_id, position in sorted(candidate.positions.items())
                )
                item = QTreeWidgetItem(
                    [
                        candidate.candidate_id[:14],
                        str(candidate.feasible_index),
                        position_text,
                    ]
                )
                item.setData(0, ROLE, candidate.candidate_id)
                tree.addTopLevelItem(item)
                if candidate.candidate_id == self.search_selected_candidate_id:
                    selected_item = item
            if selected_item is not None:
                tree.setCurrentItem(selected_item)

    def _search_candidate_selected(self) -> None:
        tree = self.search_candidate_tree
        if tree is None:
            return
        item = tree.currentItem()
        candidate_id = None if item is None else item.data(0, ROLE)
        self.search_selected_candidate_id = None if candidate_id is None else str(candidate_id)
        self._refresh_search_binding_state()
        self._render_search_overlay()

    def previous_search_page(self) -> None:
        page = self.search_candidate_page
        if page is None:
            return
        self.generate_search_candidates_async(offset=max(0, page.offset - self.search_page_limit))

    def next_search_page(self) -> None:
        page = self.search_candidate_page
        if page is None:
            return
        next_offset = page.offset + self.search_page_limit
        if next_offset < page.feasible_candidate_count:
            self.generate_search_candidates_async(offset=next_offset)

    def preview_selected_candidate(self) -> None:
        candidate = self._selected_search_candidate()
        if candidate is None:
            return
        self.search_preview_candidate_id = candidate.candidate_id
        self._refresh_search_binding_state()
        self._render_search_overlay()
        self.statusBar().showMessage('候補preview · Scene/Undo履歴は変更していません')

    def clear_candidate_preview(self) -> None:
        if self.search_preview_candidate_id is None:
            return
        self.search_preview_candidate_id = None
        self._refresh_search_binding_state()
        self._render_search_overlay()
        self.statusBar().showMessage('候補previewを解除しました')

    def apply_selected_candidate(self) -> None:
        spec = self._selected_search_spec()
        candidate = self._selected_search_candidate()
        if spec is None or candidate is None or self.working is None:
            return
        try:
            changed = apply_candidate_positions(
                self.working,
                candidate,
                spec=spec,
                current_constraint_set=self.constraint_set,
                current_document_id=self.document_id,
            )
        except Exception as exc:
            self.statusBar().showMessage(f'候補を適用できません · {exc}')
            self._refresh_search_binding_state()
            return
        if not changed:
            self.statusBar().showMessage('候補は現在配置と同一です')
            return

        entity_ids = tuple(sorted(candidate.positions))
        self.view_state.set_selection(entity_ids, primary_id=entity_ids[-1] if entity_ids else None)
        self.selected_id = self.view_state.selected_id
        self.search_preview_candidate_id = None
        self._sync_recovery()
        self._persist_view_state()
        self._rebuild()
        self._set_dirty_status()
        self._refresh_search_specs()
        self.statusBar().showMessage('候補を1 commandで適用しました · Undoで全位置を復元できます')

    def _remove_search_overlays(self) -> None:
        for name in tuple(self._search_actor_names):
            try:
                self.viewport.remove_actor(name, reset_camera=False, render=False)
            except Exception:
                pass
        self._search_actor_names.clear()

    def _render_search_overlay(self) -> None:
        self._remove_search_overlays()
        page = self.search_candidate_page
        spec = self._selected_search_spec()
        if page is None or spec is None or self.working is None:
            self.viewport.render()
            return
        if not search_spec_current_working(
            spec,
            self.working,
            self.constraint_set,
            current_document_id=self.document_id,
        ):
            self.viewport.render()
            return

        primary_entity_id = spec.axes[0].entity_id
        points = candidate_cloud_points(page, primary_entity_id)
        if len(points):
            actor_name = 'search-candidate-cloud'
            render_analysis_marker_cloud(
                self.viewport,
                points,
                actor_name=actor_name,
                point_size=6.0,
                render=False,
            )
            self._search_actor_names.add(actor_name)

        selected = self._selected_search_candidate()
        if selected is not None:
            primary = selected.positions.get(primary_entity_id)
            if primary is not None:
                name = 'search-selected-candidate'
                self._search_actor_names.add(name)
                self.viewport.add_mesh(
                    pv.Sphere(
                        radius=0.07,
                        center=(
                            float(primary['x_m']),
                            -float(primary['y_m']),
                            float(primary['z_m']),
                        ),
                    ),
                    name=name,
                    style='wireframe',
                    line_width=4,
                    pickable=False,
                    render=False,
                )

        preview = next(
            (
                candidate
                for candidate in page.candidates
                if candidate.candidate_id == self.search_preview_candidate_id
            ),
            None,
        )
        if preview is not None:
            for index, (entity_id, position) in enumerate(sorted(preview.positions.items())):
                try:
                    current = self.working.committed_document.entity(entity_id).position
                except KeyError:
                    continue
                target = (
                    float(position['x_m']),
                    -float(position['y_m']),
                    float(position['z_m']),
                )
                source = (float(current.x_m), -float(current.y_m), float(current.z_m))
                line_name = f'search-preview-line:{index}'
                point_name = f'search-preview-point:{index}'
                self._search_actor_names.update((line_name, point_name))
                self.viewport.add_mesh(
                    pv.Line(source, target),
                    name=line_name,
                    line_width=3,
                    pickable=False,
                    render=False,
                )
                self.viewport.add_mesh(
                    pv.Sphere(radius=0.055, center=target),
                    name=point_name,
                    style='wireframe',
                    line_width=3,
                    pickable=False,
                    render=False,
                )
            label_name = 'search-preview-label'
            self._search_actor_names.add(label_name)
            self.viewport.add_text(
                '候補preview · Scene未変更',
                position='upper_right',
                font_size=9,
                name=label_name,
                render=False,
            )
        self.viewport.render()

    def _replace_constraint_set(self, constraints: tuple, *, message: str) -> bool:
        changed = super()._replace_constraint_set(constraints, message=message)
        if changed and self.search_spec_tree is not None:
            self.search_preview_candidate_id = None
            self._refresh_search_specs()
            self._render_search_overlay()
        return changed

    def save(self) -> None:
        super().save()
        if self.search_spec_tree is not None:
            self._refresh_search_entities()
            self._refresh_search_specs()
            self._render_search_overlay()

    def _rebuild(self, *, reset_camera: bool = False) -> None:
        super()._rebuild(reset_camera=reset_camera)
        if self.search_spec_tree is not None:
            self._refresh_search_binding_state()
            self._render_search_overlay()

    def active_search_worker_count(self) -> int:
        return sum(1 for thread, _worker in self._search_tasks.values() if thread.isRunning())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        for thread, worker in tuple(self._search_tasks.values()):
            worker.cancel()
            thread.requestInterruption()
            thread.quit()
            thread.wait(1800)
        super().closeEvent(event)
