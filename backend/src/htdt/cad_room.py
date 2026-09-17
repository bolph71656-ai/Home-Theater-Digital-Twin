from __future__ import annotations

from dataclasses import dataclass

from .cad_document import EditStateError, WorkingDocument
from .cad_scene import RoomPrism, SceneDocument, scene_content_hash


@dataclass(frozen=True)
class ReplaceRoomCommand:
    """Replace the room atomically while preserving the rest of the scene snapshot."""

    before: SceneDocument
    after: SceneDocument

    @property
    def is_noop(self) -> bool:
        return self.before == self.after

    def apply(self, document: SceneDocument) -> SceneDocument:
        if document != self.before:
            raise EditStateError('room command base document changed before apply')
        return self.after

    def revert(self, document: SceneDocument) -> SceneDocument:
        if document != self.after:
            raise EditStateError('room command document changed before revert')
        return self.before


class RoomWorkingDocument(WorkingDocument):
    """WorkingDocument extension used by N30 room tools.

    Provisional sketch/vertex geometry stays in the room tool. Only a valid,
    closed RoomPrism reaches this command history.
    """

    def replace_room(self, room: RoomPrism | None) -> bool:
        if self.has_preview:
            raise EditStateError('cannot edit the room while an entity transform preview is active')
        before = self.committed_document
        after = before.model_copy(
            update={
                'schema_version': max(2, before.schema_version),
                'room': room,
            }
        )
        # model_copy(update=...) does not revalidate by design; validate the exact
        # snapshot that will become part of history before it can be committed.
        after = SceneDocument.model_validate(after.model_dump(mode='python'))
        before_hash = scene_content_hash(before)
        self._document = self._history.push(ReplaceRoomCommand(before, after), self._document)
        return scene_content_hash(self._document) != before_hash
