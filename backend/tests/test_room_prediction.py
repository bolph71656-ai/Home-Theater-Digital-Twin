from __future__ import annotations

from threading import Event

from htdt.cad_scene import F1_DOCUMENT_ID, acoustic_reference_position
from htdt.room_prediction import RoomPredictionController
from htdt.room_workspace import RoomWorkspaceController
from htdt.cad_repository import SceneRepository


def _controller(tmp_path):
    repository = SceneRepository(tmp_path / "scenes.sqlite3")
    room = RoomWorkspaceController(repository, F1_DOCUMENT_ID)
    prediction = RoomPredictionController(repository, room)
    receiver = next(
        entity.entity_id
        for entity in room.committed_document.entities
        if acoustic_reference_position(entity) is not None
    )
    return repository, room, prediction, receiver


def test_room_prediction_reuses_n70_identity_guard_and_repository(tmp_path) -> None:
    repository, room, prediction, receiver = _controller(tmp_path)

    spec = prediction.prepare_run(receiver)
    results = prediction._analyze(spec, Event())

    assert results is not None
    accepted = prediction.accept_results(spec, results)
    assert accepted == results
    stored = prediction.prediction_repository.list_run(results[0].run_id)
    assert stored == results
    assert all(
        result.scene_revision_id == room.working.source_revision_id
        and result.input_hash == spec.identity.input_hash
        and result.constraint_workspace_hash == spec.constraint_workspace_hash
        for result in stored
    )
    assert repository.latest(F1_DOCUMENT_ID) is not None
    assert prediction.result_is_current(stored[0]) is True

    prediction.dispose()


def test_room_prediction_rejects_delayed_result_after_scene_becomes_dirty(tmp_path) -> None:
    _repository, room, prediction, receiver = _controller(tmp_path)

    spec = prediction.prepare_run(receiver)
    results = prediction._analyze(spec, Event())
    assert results is not None

    room.add_object("furniture")
    assert room.is_dirty

    assert prediction.accept_results(spec, results) is None
    assert prediction.prediction_repository.list_results(F1_DOCUMENT_ID) == ()

    prediction.dispose()


def test_saved_room_prediction_becomes_stale_after_local_scene_edit(tmp_path) -> None:
    _repository, room, prediction, receiver = _controller(tmp_path)

    spec = prediction.prepare_run(receiver)
    results = prediction._analyze(spec, Event())
    assert results is not None
    accepted = prediction.accept_results(spec, results)
    assert accepted is not None
    assert prediction.result_is_current(accepted[0])

    room.add_object("furniture")

    assert prediction.result_is_current(accepted[0]) is False

    prediction.dispose()


def test_cancelled_room_prediction_token_cannot_be_persisted(tmp_path) -> None:
    _repository, _room, prediction, receiver = _controller(tmp_path)

    spec = prediction.prepare_run(receiver)
    results = prediction._analyze(spec, Event())
    assert results is not None
    prediction.job_guard.cancel(spec.token)

    assert prediction.accept_results(spec, results) is None
    assert prediction.prediction_repository.list_results(F1_DOCUMENT_ID) == ()

    prediction.dispose()
