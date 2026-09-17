from __future__ import annotations

import argparse
import gc
from pathlib import Path
import sys
import tempfile
import time

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QPushButton

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend' / 'src'))

from htdt.cad_measurement_repository import CadMeasurementRepository
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import make_f1_scene
from htdt.measurement_editor import MeasurementEditorWindow
from htdt.native_cad import TheaterEditorWindow
from htdt.rew_api import RewFrequencyResponse, RewFrequencyResponseSnapshot

from validate_n40_windows import click_action, click_actor, click_widget, drag_selected_x, foreground, pump, wait_until

if sys.platform != 'win32':
    raise SystemExit('This acceptance harness requires Windows.')

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='backslashreplace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='backslashreplace')

FIXTURE_ID = 'fixture-a13-n60'
OTHER_DOCUMENT_ID = 'fixture-a13-other'


class DelayedRewClient:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s

    def get_frequency_response_snapshot(
        self,
        measurement_uuid: str,
        *,
        ppo=None,
        unit='SPL',
        smoothing=None,
    ) -> RewFrequencyResponseSnapshot:
        time.sleep(self.delay_s)
        decoded = RewFrequencyResponse(
            measurement_id=measurement_uuid,
            unit='SPL',
            smoothing=smoothing,
            start_frequency_hz=20.0,
            points_per_octave=None,
            frequency_step_hz=20.0,
            frequency_hz=(20.0, 40.0, 60.0, 80.0),
            magnitude=(70.0, 71.0, 70.5, 69.0),
            phase_deg=None,
            requested_unit=unit,
            requested_ppo=ppo,
            requested_smoothing=smoothing,
        )
        return RewFrequencyResponseSnapshot(
            measurement_summary={'uuid': measurement_uuid, 'title': measurement_uuid},
            query={'unit': unit},
            raw_frequency_response={'unit': 'SPL', 'startFreq': 20.0, 'freqStep': 20.0},
            decoded=decoded,
        )


def find_button(window: MeasurementEditorWindow, text: str) -> QPushButton:
    for button in window.findChildren(QPushButton):
        if button.text() == text:
            return button
    raise AssertionError(f'button not found: {text}')


def configure_delayed_measurement(window: MeasurementEditorWindow, external_id: str, delay_s: float) -> None:
    window.rew_client = DelayedRewClient(delay_s)
    window.rew_combo.clear()
    window.rew_combo.addItem(external_id, external_id)
    window.rew_combo.setCurrentIndex(0)


def start_rew_read(window: MeasurementEditorWindow, app: QApplication) -> str | None:
    click_actor(window, 'point-mlp', app)
    click_widget(find_button(window, '選択REWを読込'), app)
    if not wait_until(app, lambda: window._current_rew_token_id is not None, 0.6):
        return None
    return window._current_rew_token_id


def wait_jobs_empty(window: MeasurementEditorWindow, app: QApplication, seconds: float = 2.5) -> bool:
    return wait_until(app, lambda: not window._rew_tasks, seconds)


def run_a13(app: QApplication, root: Path) -> bool:
    repository = SceneRepository(root / 'scene.sqlite3')
    revision_a = repository.save(make_f1_scene().model_copy(update={'document_id': FIXTURE_ID}), parent_revision_id=None).revision
    repository.save(make_f1_scene().model_copy(update={'document_id': OTHER_DOCUMENT_ID}), parent_revision_id=None)
    measurement_repository = CadMeasurementRepository(repository)

    window = TheaterEditorWindow(repository, FIXTURE_ID)
    foreground(window, app)
    closed = False
    heartbeat = {'count': 0}
    timer = QTimer(window)
    timer.setInterval(25)
    timer.timeout.connect(lambda: heartbeat.__setitem__('count', heartbeat['count'] + 1))
    timer.start()
    try:
        product_ok = isinstance(window, MeasurementEditorWindow)
        print('A13_PRODUCT_COMPOSITION', product_ok, flush=True)
        if not product_ok:
            return False

        # 1) Delayed A read. While the worker is running, edit and formally save B.
        configure_delayed_measurement(window, 'rew-stale-after-edit', 1.20)
        token_id = start_rew_read(window, app)
        if token_id is None:
            return False
        click_actor(window, 'speaker-fl', app)
        moved = drag_selected_x(window, app, scale=1.05)
        click_action(window, window.save_action, app)
        revision_b = repository.latest(FIXTURE_ID)
        stale_finished = wait_jobs_empty(window, app, 2.5)
        stale_not_saved = (
            moved
            and revision_b is not None
            and revision_b.revision_id != revision_a.revision_id
            and stale_finished
            and len(measurement_repository.list_measurements(FIXTURE_ID)) == 0
        )
        print('A13_EDIT_MAKES_RESULT_STALE', stale_not_saved, flush=True)
        if not stale_not_saved:
            return False

        responsive = heartbeat['count'] >= 10
        print('A13_UI_RESPONSIVE', responsive, heartbeat['count'], flush=True)
        if not responsive:
            return False

        # 2) Explicit cancel. The worker may still return, but the result must not save/apply.
        configure_delayed_measurement(window, 'rew-cancelled', 0.65)
        cancel_token_id = start_rew_read(window, app)
        if cancel_token_id is None:
            return False
        click_widget(find_button(window, '読込キャンセル'), app)
        cancelled = wait_jobs_empty(window, app, 1.8)
        cancel_ok = (
            cancelled
            and len(measurement_repository.list_measurements(FIXTURE_ID)) == 0
            and window.measurement_selected_id is None
        )
        print('A13_CANCELLED_RESULT_NOT_APPLIED', cancel_ok, flush=True)
        if not cancel_ok:
            return False

        # 3) Change active document state before delayed completion. This exercises
        # the same product apply-context guard used by a future project/document switch UI.
        configure_delayed_measurement(window, 'rew-document-switch', 0.65)
        document_token_id = start_rew_read(window, app)
        if document_token_id is None:
            return False
        window.document_id = OTHER_DOCUMENT_ID
        document_finished = wait_jobs_empty(window, app, 1.8)
        document_switch_ok = (
            document_finished
            and len(measurement_repository.list_measurements(FIXTURE_ID)) == 0
            and len(measurement_repository.list_measurements(OTHER_DOCUMENT_ID)) == 0
        )
        print('A13_DOCUMENT_SWITCH_RESULT_NOT_APPLIED', document_switch_ok, flush=True)
        if not document_switch_ok:
            return False
        window.document_id = FIXTURE_ID

        # 4) Close while another read is pending. closeEvent cancels tokens and waits
        # for bounded external reads; no QThread may survive the window.
        configure_delayed_measurement(window, 'rew-close-pending', 0.45)
        close_token_id = start_rew_read(window, app)
        if close_token_id is None:
            return False
        timer.stop()
        window.close()
        closed = True
        pump(app, 0.75)
        live_threads = [thread for thread in window.findChildren(QThread) if thread.isRunning()]
        close_ok = (
            not live_threads
            and len(measurement_repository.list_measurements(FIXTURE_ID)) == 0
        )
        print('A13_CLEAN_EXIT_NO_WORKER', close_ok, len(live_threads), flush=True)
        return close_ok
    finally:
        timer.stop()
        if not closed:
            window.close()
            pump(app, 0.70)
        window.deleteLater()
        gc.collect()
        pump(app, 0.08)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run N60 A13 Windows stale/cancel acceptance.')
    parser.add_argument('--keep-data', type=Path, default=None)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    if args.keep_data is not None:
        args.keep_data.mkdir(parents=True, exist_ok=True)
        passed = run_a13(app, args.keep_data)
    else:
        with tempfile.TemporaryDirectory(prefix='htdt-a13-', ignore_cleanup_errors=True) as temp:
            passed = run_a13(app, Path(temp))
    print('A13_RESULT', 'PASS' if passed else 'FAIL', flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
