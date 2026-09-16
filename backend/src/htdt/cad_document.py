from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from .cad_scene import (
    Position3, Quaternion4, SceneDocument, SceneEntity,
    rotate_orientation_world, rotate_position_world, scene_content_hash,
)


class EditStateError(RuntimeError):
    pass


def _replace_entity(document: SceneDocument, replacement: SceneEntity) -> SceneDocument:
    entities = tuple(replacement if item.entity_id == replacement.entity_id else item for item in document.entities)
    return document.model_copy(update={'entities': entities})


def _replace_entities(document: SceneDocument, replacements: tuple[SceneEntity, ...]) -> SceneDocument:
    mapping = {entity.entity_id: entity for entity in replacements}
    if len(mapping) != len(replacements):
        raise EditStateError('replacement entity ids must be unique')
    existing = {entity.entity_id for entity in document.entities}
    missing = set(mapping) - existing
    if missing:
        raise EditStateError(f'cannot replace unknown entities: {sorted(missing)}')
    entities = tuple(mapping.get(item.entity_id, item) for item in document.entities)
    return document.model_copy(update={'entities': entities})


def _move(document: SceneDocument, entity_id: str, position: Position3) -> SceneDocument:
    entity = document.entity(entity_id)
    return _replace_entity(document, entity.model_copy(update={'position': position}))


def _rotate(document: SceneDocument, entity_id: str, orientation: Quaternion4) -> SceneDocument:
    entity = document.entity(entity_id)
    return _replace_entity(document, entity.model_copy(update={'orientation': orientation}))


def _delete(document: SceneDocument, entity_id: str) -> SceneDocument:
    document.entity(entity_id)
    return document.model_copy(update={'entities': tuple(item for item in document.entities if item.entity_id != entity_id)})


def _insert(document: SceneDocument, index: int, entity: SceneEntity) -> SceneDocument:
    if any(item.entity_id == entity.entity_id for item in document.entities):
        raise EditStateError(f'entity already exists: {entity.entity_id}')
    entities = list(document.entities)
    entities.insert(index, entity)
    return document.model_copy(update={'entities': tuple(entities)})


class EditCommand(Protocol):
    @property
    def is_noop(self) -> bool: ...

    def apply(self, document: SceneDocument) -> SceneDocument: ...

    def revert(self, document: SceneDocument) -> SceneDocument: ...


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


@dataclass(frozen=True)
class RotateEntityCommand:
    entity_id: str
    before: Quaternion4
    after: Quaternion4

    @property
    def is_noop(self) -> bool:
        return self.before == self.after

    def apply(self, document: SceneDocument) -> SceneDocument:
        return _rotate(document, self.entity_id, self.after)

    def revert(self, document: SceneDocument) -> SceneDocument:
        return _rotate(document, self.entity_id, self.before)


@dataclass(frozen=True)
class TransformEntitiesCommand:
    before: tuple[SceneEntity, ...]
    after: tuple[SceneEntity, ...]

    @property
    def is_noop(self) -> bool:
        return self.before == self.after

    def apply(self, document: SceneDocument) -> SceneDocument:
        return _replace_entities(document, self.after)

    def revert(self, document: SceneDocument) -> SceneDocument:
        return _replace_entities(document, self.before)


@dataclass(frozen=True)
class DeleteEntityCommand:
    entity: SceneEntity
    index: int

    @property
    def is_noop(self) -> bool:
        return False

    def apply(self, document: SceneDocument) -> SceneDocument:
        return _delete(document, self.entity.entity_id)

    def revert(self, document: SceneDocument) -> SceneDocument:
        return _insert(document, self.index, self.entity)


@dataclass
class EditorViewState:
    """Non-physical editor state. Selection order is stable; selected_id is the primary item."""

    selected_id: str | None = None
    selected_ids: list[str] = field(default_factory=list)
    hidden_ids: set[str] = field(default_factory=set)
    locked_ids: set[str] = field(default_factory=set)
    transform_mode: Literal['move', 'rotate'] = 'move'
    grid_snap_enabled: bool = False
    grid_step_m: float = 0.05
    angle_snap_enabled: bool = False
    angle_step_deg: float = 15.0

    def __post_init__(self) -> None:
        if self.selected_id is not None and self.selected_id not in self.selected_ids:
            self.selected_ids.append(self.selected_id)
        self._dedupe_selection()
        if self.selected_id is None and self.selected_ids:
            self.selected_id = self.selected_ids[-1]

    @property
    def selection(self) -> tuple[str, ...]:
        return tuple(self.selected_ids)

    def set_selection(self, entity_ids: tuple[str, ...] | list[str], *, primary_id: str | None = None) -> None:
        self.selected_ids = list(entity_ids)
        self._dedupe_selection()
        if not self.selected_ids:
            self.selected_id = None
            return
        self.selected_id = primary_id if primary_id in self.selected_ids else self.selected_ids[-1]

    def select_only(self, entity_id: str | None) -> None:
        self.set_selection(() if entity_id is None else (entity_id,), primary_id=entity_id)

    def toggle_selected(self, entity_id: str) -> None:
        if entity_id in self.selected_ids:
            self.selected_ids.remove(entity_id)
            self.selected_id = self.selected_ids[-1] if self.selected_ids else None
        else:
            self.selected_ids.append(entity_id)
            self.selected_id = entity_id

    def is_selected(self, entity_id: str) -> bool:
        return entity_id in self.selected_ids

    def is_hidden(self, entity_id: str) -> bool:
        return entity_id in self.hidden_ids

    def is_locked(self, entity_id: str) -> bool:
        return entity_id in self.locked_ids

    def set_hidden(self, entity_id: str, hidden: bool) -> None:
        if hidden:
            self.hidden_ids.add(entity_id)
        else:
            self.hidden_ids.discard(entity_id)

    def set_locked(self, entity_id: str, locked: bool) -> None:
        if locked:
            self.locked_ids.add(entity_id)
        else:
            self.locked_ids.discard(entity_id)

    def sanitize(self, document: SceneDocument) -> None:
        valid = {entity.entity_id for entity in document.entities}
        self.hidden_ids.intersection_update(valid)
        self.locked_ids.intersection_update(valid)
        self.selected_ids = [entity_id for entity_id in self.selected_ids if entity_id in valid]
        self._dedupe_selection()
        if self.selected_id not in self.selected_ids:
            self.selected_id = self.selected_ids[-1] if self.selected_ids else None

    def _dedupe_selection(self) -> None:
        seen: set[str] = set()
        ordered: list[str] = []
        for entity_id in self.selected_ids:
            if entity_id not in seen:
                seen.add(entity_id)
                ordered.append(entity_id)
        self.selected_ids = ordered


class CommandHistory:
    def __init__(self) -> None:
        self._commands: list[EditCommand] = []
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

    def push(self, command: EditCommand, document: SceneDocument) -> SceneDocument:
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
    def __init__(self, document: SceneDocument, *, source_revision_id: str | None = None, saved_content_hash: str | None = None) -> None:
        self._document = document
        self._source_revision_id = source_revision_id
        self._saved_hash = saved_content_hash or scene_content_hash(document)
        self._history = CommandHistory()
        self._preview_kind: Literal['move', 'rotate'] | None = None
        self._preview_entity_ids: tuple[str, ...] = ()
        self._preview_before_entities: tuple[SceneEntity, ...] = ()
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
    def saved_content_hash(self) -> str:
        return self._saved_hash

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
    def preview_kind(self) -> Literal['move', 'rotate'] | None:
        return self._preview_kind

    @property
    def is_dirty(self) -> bool:
        return scene_content_hash(self._document) != self._saved_hash

    def _begin_preview(self, entity_ids: tuple[str, ...], kind: Literal['move', 'rotate']) -> tuple[SceneEntity, ...]:
        if self.has_preview:
            raise EditStateError('another preview is already active')
        if not entity_ids:
            raise EditStateError('preview requires at least one entity')
        if len(set(entity_ids)) != len(entity_ids):
            raise EditStateError('preview entity ids must be unique')
        entities = tuple(self._document.entity(entity_id) for entity_id in entity_ids)
        self._preview_kind = kind
        self._preview_entity_ids = entity_ids
        self._preview_before_entities = entities
        self._preview_document = self._document
        return entities

    def begin_move(self, entity_id: str) -> None:
        self._begin_preview((entity_id,), 'move')

    def begin_group_move(self, entity_ids: tuple[str, ...]) -> None:
        self._begin_preview(entity_ids, 'move')

    def preview_move(self, position: Position3) -> None:
        if not self.has_preview or self._preview_kind != 'move' or len(self._preview_before_entities) != 1:
            raise EditStateError('single-entity move preview has not started')
        replacement = self._preview_before_entities[0].model_copy(update={'position': position})
        self._preview_document = _replace_entities(self._document, (replacement,))

    def preview_group_move(self, delta_xyz: tuple[float, float, float]) -> None:
        if not self.has_preview or self._preview_kind != 'move' or not self._preview_before_entities:
            raise EditStateError('group move preview has not started')
        dx, dy, dz = (float(value) for value in delta_xyz)
        replacements = tuple(
            entity.model_copy(update={'position': Position3(
                x_m=entity.position.x_m + dx,
                y_m=entity.position.y_m + dy,
                z_m=entity.position.z_m + dz,
            )})
            for entity in self._preview_before_entities
        )
        self._preview_document = _replace_entities(self._document, replacements)

    def begin_rotate(self, entity_id: str) -> None:
        self._begin_preview((entity_id,), 'rotate')

    def begin_group_rotate(self, entity_ids: tuple[str, ...]) -> None:
        self._begin_preview(entity_ids, 'rotate')

    def preview_rotate(self, orientation: Quaternion4) -> None:
        if not self.has_preview or self._preview_kind != 'rotate' or len(self._preview_before_entities) != 1:
            raise EditStateError('single-entity rotate preview has not started')
        replacement = self._preview_before_entities[0].model_copy(update={'orientation': orientation})
        self._preview_document = _replace_entities(self._document, (replacement,))

    def preview_group_rotate(
        self,
        axis: Literal['x', 'y', 'z'],
        angle_deg: float,
        pivot: Position3,
    ) -> None:
        if not self.has_preview or self._preview_kind != 'rotate' or not self._preview_before_entities:
            raise EditStateError('group rotate preview has not started')
        replacements = tuple(
            entity.model_copy(update={
                'position': rotate_position_world(entity.position, pivot, axis, angle_deg),
                'orientation': rotate_orientation_world(entity.orientation, axis, angle_deg),
            })
            for entity in self._preview_before_entities
        )
        self._preview_document = _replace_entities(self._document, replacements)

    def commit_preview(self) -> bool:
        if not self.has_preview or self._preview_document is None or not self._preview_before_entities:
            return False
        after = tuple(self._preview_document.entity(entity.entity_id) for entity in self._preview_before_entities)
        command: EditCommand = TransformEntitiesCommand(self._preview_before_entities, after)
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

    def rotate_entity(self, entity_id: str, orientation: Quaternion4) -> bool:
        if self.has_preview:
            raise EditStateError('cannot commit a numeric rotation while a preview is active')
        before = self._document.entity(entity_id).orientation
        command = RotateEntityCommand(entity_id, before, orientation)
        before_hash = scene_content_hash(self._document)
        self._document = self._history.push(command, self._document)
        return scene_content_hash(self._document) != before_hash

    def delete_entity(self, entity_id: str) -> bool:
        if self.has_preview:
            raise EditStateError('cannot delete an entity while a preview is active')
        index = next(index for index, entity in enumerate(self._document.entities) if entity.entity_id == entity_id)
        entity = self._document.entities[index]
        before_hash = scene_content_hash(self._document)
        self._document = self._history.push(DeleteEntityCommand(entity=entity, index=index), self._document)
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
        self._preview_kind = None
        self._preview_entity_ids = ()
        self._preview_before_entities = ()
        self._preview_document = None
