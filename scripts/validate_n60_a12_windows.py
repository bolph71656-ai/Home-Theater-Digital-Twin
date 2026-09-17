from __future__ import annotations

import argparse
import gc
from pathlib import Path
import sys
import tempfile

from PySide6.QtWidgets import QApplication, QPushButton

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from htdt.cad_measurement_repository import CadMeasurementRepository
from htdt.cad_measurements import normalize_rew_text
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import make_f1_scene
from htdt.measurement_editor import MeasurementEditorWindow
from htdt.native_cad import TheaterEditorWindow
from htdt.native_editor import ROLE

from validate_n40_windows import click_action, click_global, click_widget, drag_selected_x, foreground, pump, wait_until

if sys.platform != 'win32':
    raise SystemExit('This acceptance harness requires Windows.')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='backslashreplace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='backslashreplace')

FIXTURE_ID = 'fixture-a12-n60'


def find_button(window: MeasurementEditorWindow, text: str) -> QPushButton:
    for button in window.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f'button not found: {text}')


def click_measurement(window: MeasurementEditorWindow, measurement_id: str, app: QApplication) -> bool:
    tree = window.measurement_tree
    if tree is None:
        return False
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item.data(0, ROLE) != measurement_id:
            continue
        rect = tree.visualItemRect(item)
        if rect.isEmpty():
            tree.scrollToItem(item)
            pump(app, 0.05)
            rect = tree.visualItemRect(item)
        click_global(tree.viewport().mapToGlobal(rect.center()), app)
        return wait_until(app, lambda: window.measurement_selected_id == measurement_id, 0.8)
    return False


def click_scene_entity(window: MeasurementEditorWindow, entity_id: str, app: QApplication) -> bool:
    item = window.items.get(entity_id)
    if item is None:
        return False
    tree = window.tree
    rect = tree.visualItemRect(item)
    if rect.isEmpty():
        tree.scrollToItem(item)
        pump(app, 0.05)
        rect = tree.visualItemRect(item)
    foreground(window, app)
    click_global(tree.viewport().mapToGlobal(rect.center()), app)
    return wait_until(app, lambda: window.selected_id == entity_id, 0.8)


def actor_names(window: MeasurementEditorWindow) -> set[str]:
    actors = getattr(window.viewport.renderer, 'actors', {})
    return set(actors.keys()) if hasattr(actors, 'keys') else set()


def run_a12(app: QApplication, root: Path) -> bool:
    repository = SceneRepository(root / 'scene.sqlite3')
    revision_a = repository.save(make_f1_scene().model_copy(update={'document_id': FIXTURE_ID}), parent_revision_id=None).revision
    measurement_repository = CadMeasurementRepository(repository)
    raw_a = b'Frequency SPL\n20 70.0\n40 71.5\n80 69.0\n160 68.5\n'
    record_a, dataset_a, filename_a, source_a = normalize_rew_text(
        revision_a,
        'point-mlp',
        raw_a,
        filename='a-mlp-fl.txt',
        evidence_type='measured',
        channel_role='front_left',
        source_speaker_ids=('speaker-fl',),
        routing_evidence='verified',
        imported_at='2026-09-17T10:00:00+00:00',
    )
    measurement_repository.save(record_a, dataset_a, raw_filename=filename_a, raw_bytes=source_a)

    window = TheaterEditorWindow(repository, FIXTURE_ID)
    foreground(window, app)
    try:
        product_ok = isinstance(window, MeasurementEditorWindow) and window.measurement_tree is not None and window.fr_plot is not None
        print('A12_PRODUCT_COMPOSITION', product_ok, flush=True)
        if not product_ok:
            return False

        selected_a = click_measurement(window, record_a.measurement_id, app)
        plotted_a = bool(window.fr_plot is not None and len(window.fr_plot.listDataItems()) >= 1)
        metadata_a = window.measurement_scene_label.text() if window.measurement_scene_label is not None else ''
        select_ok = selected_a and plotted_a and '現在配置と一致' in metadata_a
        print('A12_MOUSE_SELECT_SAVED_A', select_ok, flush=True)
        print('A12_OFFLINE_FR', plotted_a, flush=True)
        if not select_ok:
            return False

        if not click_scene_entity(window, 'speaker-fl', app):
            print('A12_MOUSE_SCENE_SELECT', False, flush=True)
            return False
        position_before = window.working.committed_document.entity('speaker-fl').position
        moved = drag_selected_x(window, app, scale=1.05)
        position_after = window.working.committed_document.entity('speaker-fl').position
        dirty_after_move = window.working.is_dirty
        click_action(window, window.save_action, app)
        revision_b = repository.latest(FIXTURE_ID)
        move_save_ok = (
            moved
            and position_after != position_before
            and dirty_after_move
            and revision_b is not None
            and revision_b.revision_id != revision_a.revision_id
            and not window.working.is_dirty
        )
        print('A12_MOUSE_MOVE_SAVE_B', move_save_ok, flush=True)
        if not move_save_ok or revision_b is None:
            return False

        reopened_a = measurement_repository.get_measurement(record_a.measurement_id)
        immutable_ok = (
            reopened_a == record_a
            and reopened_a.scene_revision_id == revision_a.revision_id
            and reopened_a.scene_content_hash == revision_a.content_hash
            and reopened_a.measurement_position == record_a.measurement_position
            and measurement_repository.source_revision(record_a.measurement_id).revision_id == revision_a.revision_id
        )
        print('A12_A_BINDING_IMMUTABLE', immutable_ok, flush=True)
        if not immutable_ok:
            return False

        window.measurement_selected_id = record_a.measurement_id
        window._rebuild()
        pump(app, 0.12)
        names = actor_names(window)
        scene_text = window.measurement_scene_label.text() if window.measurement_scene_label is not None else ''
        ghost_ok = (
            'measurement-ghost:speaker-fl' in names
            and 'measurement-ghost:point-mlp' in names
            and '現在配置と異なる' in scene_text
            and window.actors.get('speaker-fl') is not None
        )
        print('A12_HISTORICAL_GHOST', ghost_ok, flush=True)
        if not ghost_ok:
            return False

        if not click_scene_entity(window, 'point-mlp', app):
            print('A12_MOUSE_POINT_SELECT', False, flush=True)
            return False
        record_b = window.import_rew_text_bytes(
            b'Frequency SPL\n20 69.0\n40 70.0\n80 68.0\n160 67.5\n',
            'b-mlp-fl.txt',
        )
        dataset_b = measurement_repository.dataset_for_measurement(record_b.measurement_id)
        if dataset_b is None or window.compare_a_combo is None or window.compare_b_combo is None:
            return False
        index_a = window.compare_a_combo.findData(dataset_a.dataset_id)
        index_b = window.compare_b_combo.findData(dataset_b.dataset_id)
        if index_a < 0 or index_b < 0:
            return False
        window.compare_a_combo.setCurrentIndex(index_a)
        window.compare_b_combo.setCurrentIndex(index_b)
        click_widget(find_button(window, 'A/B比較を保存'), app)
        comparisons = measurement_repository.list_comparisons(FIXTURE_ID)
        comparison_ok = (
            len(comparisons) == 1
            and comparisons[0].dataset_a_id == dataset_a.dataset_id
            and comparisons[0].dataset_b_id == dataset_b.dataset_id
            and comparisons[0].scene_revision_a_id == revision_a.revision_id
            and comparisons[0].scene_revision_b_id == revision_b.revision_id
            and window.diff_plot is not None
            and len(window.diff_plot.listDataItems()) >= 1
        )
        print('A12_AB_REVISION_BINDING', comparison_ok, flush=True)
        return comparison_ok
    finally:
        window.close()
        pump(app, 0.12)
        window.deleteLater()
        gc.collect()
        pump(app, 0.08)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run N60 A12 Windows acceptance with real OS mouse input.')
    parser.add_argument('--keep-data', type=Path, default=None)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    if args.keep_data is not None:
        args.keep_data.mkdir(parents=True, exist_ok=True)
        passed = run_a12(app, args.keep_data)
    else:
        with tempfile.TemporaryDirectory(prefix='htdt-a12-', ignore_cleanup_errors=True) as temp:
            passed = run_a12(app, Path(temp))
    print('A12_RESULT', 'PASS' if passed else 'FAIL', flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
