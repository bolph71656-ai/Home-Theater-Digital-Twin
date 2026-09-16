from __future__ import annotations

from dataclasses import dataclass

from .cad_scene import Position3, SceneDocument, SceneEntity, scene_content_hash


class EditStateError(RuntimeError):
    pass


def _replace_entity(document: SceneDocument, replacement: SceneEntity) -> SceneDocument:
    entities = tuple(replacement if item.entity_id == replacement.entity_id else item for item in document.entities)
    return document.model_copy(update={'entities': entities})


def _move(document: SceneDocument, entity_id: str, position: Position3) -> SceneDocument:
    entity = document.entity(entity_id)
    return _replace_entity(document, entity.model_copy(update={'position': position}))


@dataclass(frozen=True)
class MoveEntityCommand:
    entity_id: str
    before: Position3
    after: Position3

    @property
    def is_noop(self) -> bool:
        return self.before == self.after

    def apply(self, document: SceneDocument) -> SceneDocument:
        return _move(document, self.entity_id, self.after)

    def revert(self, document: SceneDocument) -> SceneDocument:
        return _move(document, self.entity_id, self.before)


class CommandHistory:
    def __init__(self) -> None:
        self._commands: list[MoveEntityCommand] = []
        self._index = 0

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._commands)

    @property
    def length(self) -> int:
        return len(self._commands)

    def push(self, command: MoveEntityCommand, document: SceneDocument) -> SceneDocument:
        if command.is_noop:
            return document
        self._commands = self._commands[: self._index]
        self._commands.append(command)
        self._index += 1
        return command.apply(document)

    def undo(self, document: SceneDocument) -> SceneDocument:
        if not self.can_undo:
            return document
        self._index -= 1
        return self._commands[self._index].revert(document)

    def redo(self, document: SceneDocument) -> SceneDocument:
        if not self.can_redo:
            return document
        command = self._commands[self._index]
        self._index += 1
        return command.apply(document)


class WorkingDocument:
    def __init__(self, document: SceneDocument, *, source_revision_id: str | None = None) -> None:
        self._document = document
        self._source_revision_id = source_revision_id
        self._saved_hash = scene_content_hash(document)
        self._history = CommandHistory()
        self._preview_entity_id: str | None = None
        self._preview_before: Position3 | None = None
        self._preview_document: SceneDocument | None = None

    @property
    def document(self) -> SceneDocument:
        return self._preview_document or self._document

    @property
    def committed_document(self) -> SceneDocument:
        return self._document

    @property
    def source_revision_id(self) -> str | None:
        return self._source_revision_id

    @property
    def history_length(self) -> int:
        return self._history.length

    @property
    def can_undo(self) -> bool:
        return self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._history.can_redo

    @property
    def has_preview(self) -> bool:
        return self._preview_document is not None

    @property
    def is_dirty(self) -> bool:
        return scene_content_hash(self._document) != self._saved_hash

    def begin_move(self, entity_id: str) -> None:
        if self.has_preview:
            raise EditStateError('another preview is already active')
        self._preview_entity_id = entity_id
        self._preview_before = self._document.entity(entity_id).position
        self._preview_document = self._document

    def preview_move(self, position: Position3) -> None:
        if not self.has_preview or self._preview_entity_id is None:
            raise EditStateError('move preview has not started')
        self._preview_document = _move(self._document, self._preview_entity_id, position)

    def commit_preview(self) -> bool:
        if not self.has_preview or self._preview_entity_id is None or self._preview_before is None:
            return False
        after = self._preview_document.entity(self._preview_entity_id).position
        command = MoveEntityCommand(self._preview_entity_id, self._preview_before, after)
        self._clear_preview()
        before_hash = scene_content_hash(self._document)
        self._document = self._history.push(command, self._document)
        return scene_content_hash(self._document) != before_hash

    def cancel_preview(self) -> bool:
        if not self.has_preview:
            return False
        self._clear_preview()
        return True

    def move_entity(self, entity_id: str, position: Position3) -> bool:
        if self.has_preview:
            raise EditStateError('cannot commit a numeric move while a preview is active')
        before = self._document.entity(entity_id).position
        command = MoveEntityCommand(entity_id, before, position)
        before_hash = scene_content_hash(self._document)
        self._document = self._history.push(command, self._document)
        return scene_content_hash(self._document) != before_hash

    def undo(self) -> bool:
        if self.has_preview:
            raise EditStateError('cancel the active preview before undo')
        before_hash = scene_content_hash(self._document)
        self._document = self._history.undo(self._document)
        return scene_content_hash(self._document) != before_hash

    def redo(self) -> bool:
        if self.has_preview:
            raise EditStateError('cancel the active preview before redo')
        before_hash = scene_content_hash(self._document)
        self._document = self._history.redo(self._document)
        return scene_content_hash(self._document) != before_hash

    def mark_saved(self, revision_id: str, content_hash: str) -> None:
        if self.has_preview:
            raise EditStateError('cannot mark a document saved while a preview is active')
        actual = scene_content_hash(self._document)
        if actual != content_hash:
            raise EditStateError('saved content hash does not match the working document')
        self._source_revision_id = revision_id
        self._saved_hash = actual

    def _clear_preview(self) -> None:
        self._preview_entity_id = None
        self._preview_before = None
        self._preview_document = None
