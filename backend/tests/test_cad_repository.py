from pathlib import Path

import pytest

from htdt.cad_document import WorkingDocument
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, make_f1_scene


def test_scene_revision_save_reopen_noop_and_parent_history(tmp_path: Path) -> None:
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    first = repository.save(make_f1_scene(), parent_revision_id=None)
    assert first.created

    working = WorkingDocument(
        first.revision.document,
        source_revision_id=first.revision.revision_id,
        saved_content_hash=first.revision.content_hash,
    )
    assert not working.is_dirty

    working.move_entity('speaker-fl', Position3(x_m=1.5, y_m=0.75, z_m=1.05))
    assert working.is_dirty
    second = repository.save(working.committed_document, parent_revision_id=working.source_revision_id)
    assert second.created
    working.mark_saved(second.revision.revision_id, second.revision.content_hash)
    assert not working.is_dirty

    reopened = repository.latest(make_f1_scene().document_id)
    assert reopened is not None
    assert reopened.revision_id == second.revision.revision_id
    assert reopened.document.entity('speaker-fl').position.x_m == 1.5
    first_reopened = repository.get(first.revision.revision_id)
    assert first_reopened is not None
    assert first_reopened.document.entity('speaker-fl').position.x_m == 1.35

    noop = repository.save(reopened.document, parent_revision_id=reopened.revision_id)
    assert not noop.created
    assert noop.revision.revision_id == reopened.revision_id

    restored = WorkingDocument(
        reopened.document,
        source_revision_id=reopened.revision_id,
        saved_content_hash=reopened.content_hash,
    )
    restored.move_entity('speaker-fl', Position3(x_m=1.35, y_m=0.75, z_m=1.05))
    third = repository.save(restored.committed_document, parent_revision_id=reopened.revision_id)
    assert third.created
    assert third.revision.parent_revision_id == reopened.revision_id
    assert third.revision.content_hash == first.revision.content_hash


def test_recovery_is_separate_from_formal_revision_and_formal_save_clears_it(tmp_path: Path) -> None:
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    first = repository.save(make_f1_scene(), parent_revision_id=None).revision
    working = WorkingDocument(
        first.document,
        source_revision_id=first.revision_id,
        saved_content_hash=first.content_hash,
    )
    working.move_entity('speaker-fl', Position3(x_m=1.6, y_m=0.75, z_m=1.05))

    recovery = repository.save_recovery(
        working.committed_document,
        source_revision_id=working.source_revision_id,
    )
    assert recovery is not None
    assert recovery.document.entity('speaker-fl').position.x_m == 1.6
    assert repository.latest(first.document_id).revision_id == first.revision_id

    reopened_recovery = repository.recovery(first.document_id)
    assert reopened_recovery is not None
    recovered_working = WorkingDocument(
        reopened_recovery.document,
        source_revision_id=first.revision_id,
        saved_content_hash=first.content_hash,
    )
    assert recovered_working.is_dirty

    saved = repository.save(
        recovered_working.committed_document,
        parent_revision_id=recovered_working.source_revision_id,
    )
    assert saved.created
    assert repository.recovery(first.document_id) is None
    first_after = repository.get(first.revision_id)
    assert first_after is not None
    assert first_after.document.entity('speaker-fl').position.x_m == 1.35


def test_failed_save_does_not_change_working_document_or_formal_revision(tmp_path: Path) -> None:
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    first = repository.save(make_f1_scene(), parent_revision_id=None).revision
    working = WorkingDocument(
        first.document,
        source_revision_id=first.revision_id,
        saved_content_hash=first.content_hash,
    )
    working.move_entity('speaker-fl', Position3(x_m=1.7, y_m=0.75, z_m=1.05))
    before = working.committed_document
    history_length = working.history_length

    with pytest.raises(ValueError, match='unknown parent revision'):
        repository.save(before, parent_revision_id='missing-revision')

    assert working.committed_document == before
    assert working.history_length == history_length
    assert working.is_dirty
    assert repository.latest(first.document_id).revision_id == first.revision_id


def test_editor_view_state_round_trip_is_not_part_of_scene_revision(tmp_path: Path) -> None:
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    first = repository.save(make_f1_scene(), parent_revision_id=None).revision

    repository.save_view_state(
        first.document_id,
        selected_id='speaker-fl',
        hidden_ids={'speaker-fr'},
        locked_ids={'speaker-fl', 'speaker-c'},
    )
    state = repository.view_state(first.document_id)

    assert state is not None
    assert state.selected_id == 'speaker-fl'
    assert state.hidden_ids == ('speaker-fr',)
    assert state.locked_ids == ('speaker-c', 'speaker-fl')
    assert repository.latest(first.document_id).content_hash == first.content_hash
