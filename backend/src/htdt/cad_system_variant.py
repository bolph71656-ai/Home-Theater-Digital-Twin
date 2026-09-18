from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Literal, Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cad_document import WorkingDocument
from .cad_repository import SceneRevision
from .cad_scene import SceneDocument, SceneEntity, scene_content_hash


SYSTEM_VARIANT_SCHEMA_VERSION = 1
SYSTEM_VARIANT_AUTHORITY_VERSION = 'o100a-system-variant-1'

LifecycleState = Literal['current', 'proposed', 'as_built', 'measured']
VariantDiffKind = Literal['add', 'remove', 'replace']
ProposalEvidenceKind = Literal[
    'prediction',
    'objective',
    'robustness',
    'comparison',
    'user_decision',
]


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode('utf-8')).hexdigest()


class VariantProvenanceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class ChannelRoleBinding(BaseModel):
    """Versioned role identity without imposing a fixed speaker-role schema."""

    model_config = ConfigDict(frozen=True)

    role_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    layout_profile_id: str | None = Field(default=None, min_length=1)
    layout_profile_version: str | None = Field(default=None, min_length=1)
    paired_role_id: str | None = Field(default=None, min_length=1)
    provenance: tuple[VariantProvenanceItem, ...] = ()

    @model_validator(mode='after')
    def valid_role(self) -> 'ChannelRoleBinding':
        if self.paired_role_id == self.role_id:
            raise ValueError('channel role cannot be paired with itself')
        if (self.layout_profile_id is None) != (self.layout_profile_version is None):
            raise ValueError('layout profile id/version must be supplied together')
        keys = [item.key for item in self.provenance]
        if len(keys) != len(set(keys)):
            raise ValueError('channel role provenance keys must be unique')
        return self


class ProposedEntitySpec(BaseModel):
    """Exact hypothetical speaker payload. No measurement/equipment authority lives here."""

    model_config = ConfigDict(frozen=True)

    spec_id: str = Field(min_length=1)
    entity: SceneEntity
    role_binding_id: str = Field(min_length=1)
    lifecycle: Literal['proposed'] = 'proposed'
    provenance: tuple[VariantProvenanceItem, ...] = ()

    @model_validator(mode='after')
    def valid_proposed_entity(self) -> 'ProposedEntitySpec':
        if self.entity.kind != 'speaker':
            raise ValueError('O100A ProposedEntitySpec currently supports speaker entities only')
        if self.entity.speaker_role != self.role_binding_id:
            raise ValueError('proposed speaker role must match ChannelRoleBinding role_id')
        keys = [item.key for item in self.provenance]
        if len(keys) != len(set(keys)):
            raise ValueError('proposed entity provenance keys must be unique')
        return self


class ProposalEvidenceRef(BaseModel):
    """Reference to proposal evidence; physical measurement is intentionally not a valid kind."""

    model_config = ConfigDict(frozen=True)

    evidence_kind: ProposalEvidenceKind
    evidence_id: str = Field(min_length=1)
    evidence_sha256: str | None = Field(
        default=None,
        pattern=r'^[0-9a-f]{64}$',
    )
    detail: str | None = Field(default=None, min_length=1)


class EntityLifecycleBinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(min_length=1)
    state: LifecycleState
    measurement_ids: tuple[str, ...] = ()

    @model_validator(mode='after')
    def valid_measurement_state(self) -> 'EntityLifecycleBinding':
        if len(self.measurement_ids) != len(set(self.measurement_ids)):
            raise ValueError('measurement ids must be unique')
        if self.state == 'measured' and not self.measurement_ids:
            raise ValueError('measured lifecycle state requires measurement evidence')
        if self.state != 'measured' and self.measurement_ids:
            raise ValueError('measurement evidence is valid only for measured lifecycle state')
        return self


class VariantEntityDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: VariantDiffKind
    entity_id: str = Field(min_length=1)
    before_entity: SceneEntity | None = None
    after_entity: SceneEntity | None = None
    insertion_index: int = Field(ge=0)

    @model_validator(mode='after')
    def valid_diff(self) -> 'VariantEntityDiff':
        before = self.before_entity
        after = self.after_entity
        if self.kind == 'add':
            if before is not None or after is None:
                raise ValueError('add diff requires only after_entity')
        elif self.kind == 'remove':
            if before is None or after is not None:
                raise ValueError('remove diff requires only before_entity')
        else:
            if before is None or after is None:
                raise ValueError('replace diff requires before_entity and after_entity')
        for entity in (before, after):
            if entity is not None and entity.entity_id != self.entity_id:
                raise ValueError('variant diff entity_id mismatch')
        return self


class SystemVariant(BaseModel):
    """Immutable O100A system proposal bound to one exact baseline SceneRevision."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = SYSTEM_VARIANT_SCHEMA_VERSION
    authority_version: Literal['o100a-system-variant-1'] = SYSTEM_VARIANT_AUTHORITY_VERSION
    variant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    baseline_revision_id: str = Field(min_length=1)
    baseline_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    parent_variant_id: str | None = Field(default=None, min_length=1)
    role_bindings: tuple[ChannelRoleBinding, ...]
    proposed_entities: tuple[ProposedEntitySpec, ...]
    diff: tuple[VariantEntityDiff, ...]
    entity_lifecycle: tuple[EntityLifecycleBinding, ...]
    proposal_evidence: tuple[ProposalEvidenceRef, ...] = ()
    provenance: tuple[VariantProvenanceItem, ...] = ()
    created_at_utc: str = Field(min_length=1)
    variant_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_variant(self) -> 'SystemVariant':
        role_ids = [item.role_id for item in self.role_bindings]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError('SystemVariant role bindings must be unique')
        spec_ids = [item.spec_id for item in self.proposed_entities]
        if len(spec_ids) != len(set(spec_ids)):
            raise ValueError('SystemVariant proposed entity spec ids must be unique')
        proposed_entity_ids = [item.entity.entity_id for item in self.proposed_entities]
        if len(proposed_entity_ids) != len(set(proposed_entity_ids)):
            raise ValueError('SystemVariant proposed entity ids must be unique')
        role_set = set(role_ids)
        for item in self.proposed_entities:
            if item.role_binding_id not in role_set:
                raise ValueError('proposed entity references unknown ChannelRoleBinding')
        diff_ids = [item.entity_id for item in self.diff]
        if len(diff_ids) != len(set(diff_ids)):
            raise ValueError('SystemVariant diff entity ids must be unique')
        lifecycle_ids = [item.entity_id for item in self.entity_lifecycle]
        if len(lifecycle_ids) != len(set(lifecycle_ids)):
            raise ValueError('SystemVariant lifecycle bindings must be unique')
        proposed_set = set(proposed_entity_ids)
        for item in self.entity_lifecycle:
            if item.entity_id in proposed_set and item.state != 'proposed':
                raise ValueError('ProposedEntitySpec must remain in proposed lifecycle state')
        provenance_keys = [item.key for item in self.provenance]
        if len(provenance_keys) != len(set(provenance_keys)):
            raise ValueError('SystemVariant provenance keys must be unique')
        if self.variant_sha256 != _digest(self.identity_payload()):
            raise ValueError('SystemVariant identity hash mismatch')
        return self

    def identity_payload(self) -> dict[str, Any]:
        return {
            'schema_version': self.schema_version,
            'authority_version': self.authority_version,
            'name': self.name,
            'document_id': self.document_id,
            'baseline_revision_id': self.baseline_revision_id,
            'baseline_content_hash': self.baseline_content_hash,
            'parent_variant_id': self.parent_variant_id,
            'role_bindings': [item.model_dump(mode='json') for item in self.role_bindings],
            'proposed_entities': [item.model_dump(mode='json') for item in self.proposed_entities],
            'diff': [item.model_dump(mode='json') for item in self.diff],
            'entity_lifecycle': [item.model_dump(mode='json') for item in self.entity_lifecycle],
            'proposal_evidence': [item.model_dump(mode='json') for item in self.proposal_evidence],
            'provenance': [item.model_dump(mode='json') for item in self.provenance],
        }


def _validate_baseline(variant: SystemVariant, baseline: SceneRevision) -> None:
    if baseline.revision_id != variant.baseline_revision_id:
        raise ValueError('SystemVariant baseline revision mismatch')
    if baseline.document_id != variant.document_id:
        raise ValueError('SystemVariant baseline document mismatch')
    if baseline.content_hash != variant.baseline_content_hash:
        raise ValueError('SystemVariant baseline content hash mismatch')


def materialize_system_variant(
    baseline: SceneRevision,
    variant: SystemVariant,
) -> SceneDocument:
    """Derive the exact proposed scene without mutating the baseline revision."""

    _validate_baseline(variant, baseline)
    entities = list(baseline.document.entities)
    by_id = {entity.entity_id: entity for entity in entities}

    for change in variant.diff:
        if change.kind == 'add':
            continue
        existing = by_id.get(change.entity_id)
        if existing is None:
            raise ValueError(f'variant diff references missing baseline entity: {change.entity_id}')
        if existing != change.before_entity:
            raise ValueError(f'variant diff before_entity mismatch: {change.entity_id}')
        index = entities.index(existing)
        if index != change.insertion_index:
            raise ValueError(f'variant diff baseline index mismatch: {change.entity_id}')
        if change.kind == 'remove':
            entities.pop(index)
            del by_id[change.entity_id]
        else:
            assert change.after_entity is not None
            entities[index] = change.after_entity
            by_id[change.entity_id] = change.after_entity

    for change in variant.diff:
        if change.kind != 'add':
            continue
        if change.entity_id in by_id:
            raise ValueError(f'variant add duplicates entity_id: {change.entity_id}')
        if change.after_entity is None:
            raise ValueError('variant add is missing after_entity')
        if change.insertion_index != len(entities):
            raise ValueError('variant add insertion index no longer matches exact derivation')
        entities.append(change.after_entity)
        by_id[change.entity_id] = change.after_entity

    return baseline.document.model_copy(update={'entities': tuple(entities)})


def build_system_variant(
    *,
    baseline: SceneRevision,
    name: str,
    role_bindings: Sequence[ChannelRoleBinding],
    proposed_entities: Sequence[ProposedEntitySpec],
    remove_entity_ids: Sequence[str] = (),
    lifecycle_overrides: Sequence[EntityLifecycleBinding] = (),
    proposal_evidence: Sequence[ProposalEvidenceRef] = (),
    provenance: Sequence[VariantProvenanceItem] = (),
    parent_variant_id: str | None = None,
    created_at_utc: str,
) -> SystemVariant:
    """Create an exact add/remove/replace proposal from a fixed SceneRevision."""

    roles = tuple(role_bindings)
    proposals = tuple(proposed_entities)
    removals = tuple(dict.fromkeys(remove_entity_ids))
    evidence = tuple(proposal_evidence)
    provenance_items = tuple(provenance)

    baseline_entities = {entity.entity_id: entity for entity in baseline.document.entities}
    proposal_by_id = {item.entity.entity_id: item for item in proposals}
    if len(proposal_by_id) != len(proposals):
        raise ValueError('proposed entity ids must be unique')
    overlap = set(removals).intersection(proposal_by_id)
    if overlap:
        raise ValueError(f'entity cannot be both removed and proposed: {sorted(overlap)}')
    missing_removals = set(removals) - set(baseline_entities)
    if missing_removals:
        raise ValueError(f'cannot remove missing baseline entities: {sorted(missing_removals)}')

    role_by_id = {item.role_id: item for item in roles}
    if len(role_by_id) != len(roles):
        raise ValueError('ChannelRoleBinding role ids must be unique')
    for proposal in proposals:
        if proposal.role_binding_id not in role_by_id:
            raise ValueError('proposed entity references unknown ChannelRoleBinding')

    diff: list[VariantEntityDiff] = []
    for index, entity in enumerate(baseline.document.entities):
        if entity.entity_id in removals:
            diff.append(VariantEntityDiff(
                kind='remove',
                entity_id=entity.entity_id,
                before_entity=entity,
                insertion_index=index,
            ))
            continue
        proposal = proposal_by_id.get(entity.entity_id)
        if proposal is not None:
            diff.append(VariantEntityDiff(
                kind='replace',
                entity_id=entity.entity_id,
                before_entity=entity,
                after_entity=proposal.entity,
                insertion_index=index,
            ))

    final_count_before_add = len(baseline.document.entities) - len(removals)
    add_offset = 0
    for proposal in proposals:
        if proposal.entity.entity_id in baseline_entities:
            continue
        diff.append(VariantEntityDiff(
            kind='add',
            entity_id=proposal.entity.entity_id,
            after_entity=proposal.entity,
            insertion_index=final_count_before_add + add_offset,
        ))
        add_offset += 1

    overrides = {item.entity_id: item for item in lifecycle_overrides}
    if len(overrides) != len(tuple(lifecycle_overrides)):
        raise ValueError('lifecycle override entity ids must be unique')
    if set(overrides).intersection(proposal_by_id):
        raise ValueError('proposed entity lifecycle cannot be overridden')
    valid_final_ids = (
        (set(baseline_entities) - set(removals))
        | set(proposal_by_id)
    )
    unknown_overrides = set(overrides) - valid_final_ids
    if unknown_overrides:
        raise ValueError(f'lifecycle override references missing final entity: {sorted(unknown_overrides)}')

    lifecycle: list[EntityLifecycleBinding] = []
    final_speakers: list[str] = []
    for entity in baseline.document.entities:
        if entity.entity_id in removals:
            continue
        replacement = proposal_by_id.get(entity.entity_id)
        effective = replacement.entity if replacement is not None else entity
        if effective.kind == 'speaker':
            final_speakers.append(effective.entity_id)
    final_speakers.extend(
        item.entity.entity_id
        for item in proposals
        if item.entity.entity_id not in baseline_entities
    )
    for entity_id in final_speakers:
        if entity_id in proposal_by_id:
            lifecycle.append(EntityLifecycleBinding(entity_id=entity_id, state='proposed'))
        else:
            lifecycle.append(overrides.get(
                entity_id,
                EntityLifecycleBinding(entity_id=entity_id, state='current'),
            ))

    identity = {
        'schema_version': SYSTEM_VARIANT_SCHEMA_VERSION,
        'authority_version': SYSTEM_VARIANT_AUTHORITY_VERSION,
        'name': name,
        'document_id': baseline.document_id,
        'baseline_revision_id': baseline.revision_id,
        'baseline_content_hash': baseline.content_hash,
        'parent_variant_id': parent_variant_id,
        'role_bindings': [item.model_dump(mode='json') for item in roles],
        'proposed_entities': [item.model_dump(mode='json') for item in proposals],
        'diff': [item.model_dump(mode='json') for item in diff],
        'entity_lifecycle': [item.model_dump(mode='json') for item in lifecycle],
        'proposal_evidence': [item.model_dump(mode='json') for item in evidence],
        'provenance': [item.model_dump(mode='json') for item in provenance_items],
    }
    return SystemVariant(
        variant_id=str(uuid4()),
        name=name,
        document_id=baseline.document_id,
        baseline_revision_id=baseline.revision_id,
        baseline_content_hash=baseline.content_hash,
        parent_variant_id=parent_variant_id,
        role_bindings=roles,
        proposed_entities=proposals,
        diff=tuple(diff),
        entity_lifecycle=tuple(lifecycle),
        proposal_evidence=evidence,
        provenance=provenance_items,
        created_at_utc=created_at_utc,
        variant_sha256=_digest(identity),
    )


def apply_system_variant_to_working_document(
    working: WorkingDocument,
    *,
    baseline: SceneRevision,
    variant: SystemVariant,
) -> bool:
    """Apply a proposal to WorkingDocument as one undoable command, without saving it."""

    _validate_baseline(variant, baseline)
    if working.source_revision_id != baseline.revision_id:
        raise ValueError('working document is not based on the SystemVariant baseline')
    if scene_content_hash(working.committed_document) != baseline.content_hash:
        raise ValueError('working document has diverged from the SystemVariant baseline')
    proposed = materialize_system_variant(baseline, variant)
    return working.replace_document(proposed)
