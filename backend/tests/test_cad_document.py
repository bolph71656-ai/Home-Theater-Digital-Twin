from htdt.cad_document import WorkingDocument
from htdt.cad_scene import Position3, domain_to_render, make_f1_scene, render_delta_to_domain


def test_preview_cancel_does_not_change_history_or_unknown_aim() -> None:
    working = WorkingDocument(make_f1_scene())
    original = working.committed_document.entity('speaker-fl')
    working.begin_move('speaker-fl')
    working.preview_move(Position3(x_m=1.5, y_m=0.8, z_m=1.05))
    assert working.document.entity('speaker-fl').position.x_m == 1.5
    assert working.cancel_preview()
    assert working.history_length == 0
    current = working.committed_document.entity('speaker-fl')
    assert current.position == original.position
    assert current.aim_xyz is None


def test_drag_commit_is_one_undo_and_numeric_move_uses_same_history() -> None:
    working = WorkingDocument(make_f1_scene())
    original = working.committed_document.entity('speaker-fl').position
    working.begin_move('speaker-fl')
    working.preview_move(Position3(x_m=1.55, y_m=0.75, z_m=1.05))
    assert working.commit_preview()
    assert working.history_length == 1
    assert working.undo()
    assert working.committed_document.entity('speaker-fl').position == original
    assert working.redo()
    assert working.move_entity('speaker-fl', Position3(x_m=1.60, y_m=0.75, z_m=1.05))
    assert working.history_length == 2


def test_noop_move_is_not_added_to_history() -> None:
    working = WorkingDocument(make_f1_scene())
    position = working.committed_document.entity('speaker-fl').position
    assert not working.move_entity('speaker-fl', position)
    assert working.history_length == 0


def test_domain_render_coordinate_mapping_is_explicit_and_reversible() -> None:
    base = Position3(x_m=1.0, y_m=2.0, z_m=3.0)
    assert domain_to_render(base) == (1.0, -2.0, 3.0)
    moved = render_delta_to_domain((0.25, -0.5, 0.75), base)
    assert moved == Position3(x_m=1.25, y_m=2.5, z_m=3.75)
