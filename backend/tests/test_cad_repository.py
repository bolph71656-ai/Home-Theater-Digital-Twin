from pathlib import Path

from htdt.cad_document import WorkingDocument
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import Position3, make_f1_scene


def test_scene_revision_save_reopen_noop_and_parent_history(tmp_path: Path) -> None:
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    first = repository.save(make_f1_scene(), parent_revision_id=None)
    assert first.created

    working = WorkingDocument(first.revision.document, source_revision_id=first.revision.revision_id)
    working.mark_saved(first.revision.revision_id, first.revision.content_hash)
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
    assert repository.get(first.revision.revision_id).document.entity('speaker-fl').position.x_m == 1.35

    noop = repository.save(reopened.document, parent_revision_id=reopened.revision_id)
    assert not noop.created
    assert noop.revision.revision_id == reopened.revision_id

    restored = WorkingDocument(reopened.document, source_revision_id=reopened.revision_id)
    restored.move_entity('speaker-fl', Position3(x_m=1.35, y_m=0.75, z_m=1.05))
    third = repository.save(restored.committed_document, parent_revision_id=reopened.revision_id)
    assert third.created
    assert third.revision.parent_revision_id == reopened.revision_id
    assert third.revision.content_hash == first.revision.content_hash
