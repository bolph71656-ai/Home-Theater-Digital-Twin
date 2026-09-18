from __future__ import annotations

from pathlib import Path

import pytest

from htdt.cad_constraint_models import (
    CadConstraintPoint2D,
    CadConstraintSet,
)
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import (
    Direction3,
    Position3,
    RoomPrism,
    SceneDocument,
    SceneEntity,
    Size3,
)
from htdt.cad_search_models import CadSearchAxis
from htdt.cad_system_variant import (
    ChannelRoleBinding,
    ProposedEntitySpec,
    build_system_variant,
)
from htdt.cad_system_variant_repository import CadSystemVariantRepository
from htdt.cad_topology_search import (
    LinkedPlacementRule,
    PlacementAngleAxis,
    ProposedExclusionRegion,
    ProposedPlacementSpec,
    build_topology_placement_search_spec,
    generate_topology_placement_candidates,
    topology_candidate_document,
    topology_candidate_to_system_variant,
)
from htdt.cad_topology_search_repository import CadTopologySearchRepository
from htdt.cad_topology_space import build_topology_search_spec


DOCUMENT_ID = 'o100b-virtual-placement-fixture'
NOW = '2026-09-19T00:00:00+00:00'


def _speaker(
    entity_id: str,
    role: str,
    x_m: float,
    y_m: float,
    z_m: float,
    *,
    size: Size3 | None = None,
) -> SceneEntity:
    return SceneEntity(
        entity_id=entity_id,
        kind='speaker',
        name=role,
        speaker_role=role,
        position=Position3(x_m=x_m, y_m=y_m, z_m=z_m),
        size_m=size or Size3(x_m=0.24, y_m=0.28, z_m=0.42),
        aim_xyz=Direction3(x=0.0, y=1.0, z=0.0),
    )


def _scene_302(document_id: str = DOCUMENT_ID) -> SceneDocument:
    return SceneDocument(
        document_id=document_id,
        room=RoomPrism(width_m=6.0, depth_m=4.5, height_m=2.4),
        entities=(
            _speaker('fl', 'FL', 1.2, 0.8, 1.0),
            _speaker('c', 'C', 3.0, 0.6, 0.9),
            _speaker('fr', 'FR', 4.8, 0.8, 1.0),
            _speaker('tfl', 'TFL', 1.8, 2.0, 2.2),
            _speaker('tfr', 'TFR', 4.2, 2.0, 2.2),
            SceneEntity(
                entity_id='mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=3.0, y_m=3.2, z_m=1.1),
            ),
        ),
    )


def _roles_with_surround_pair() -> tuple[ChannelRoleBinding, ...]:
    return (
        ChannelRoleBinding(role_id='FL', display_name='FL'),
        ChannelRoleBinding(role_id='C', display_name='C'),
        ChannelRoleBinding(role_id='FR', display_name='FR'),
        ChannelRoleBinding(role_id='TFL', display_name='TFL'),
        ChannelRoleBinding(role_id='TFR', display_name='TFR'),
        ChannelRoleBinding(
            role_id='SL',
            display_name='SL',
            paired_role_id='SR',
        ),
        ChannelRoleBinding(
            role_id='SR',
            display_name='SR',
            paired_role_id='SL',
        ),
    )


def _proposal(entity_id: str, role: str, x_m: float) -> ProposedEntitySpec:
    return ProposedEntitySpec(
        spec_id=f'proposal-{entity_id}',
        entity=_speaker(entity_id, role, x_m, 2.9, 1.3),
        role_binding_id=role,
    )


def _region(
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
) -> tuple[CadConstraintPoint2D, ...]:
    return (
        CadConstraintPoint2D(x_m=min_x, y_m=min_y),
        CadConstraintPoint2D(x_m=max_x, y_m=min_y),
        CadConstraintPoint2D(x_m=max_x, y_m=max_y),
        CadConstraintPoint2D(x_m=min_x, y_m=max_y),
    )


def _baseline(tmp_path: Path, document: SceneDocument | None = None):
    repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision = repository.save(
        document or _scene_302(),
        parent_revision_id=None,
    ).revision
    return repository, revision


def test_302_to_502_pair_search_is_reproducible_and_persistable(
    tmp_path: Path,
) -> None:
    scene_repository, baseline = _baseline(tmp_path)
    before = baseline.document
    template = build_system_variant(
        baseline=baseline,
        name='Proposed 5.0.2 placement template',
        role_bindings=_roles_with_surround_pair(),
        proposed_entities=(
            _proposal('sl', 'SL', 0.8),
            _proposal('sr', 'SR', 5.2),
        ),
        created_at_utc=NOW,
    )
    variant_repository = CadSystemVariantRepository(scene_repository)
    variant_repository.save_variant(template)
    topology = build_topology_search_spec(
        baseline=baseline,
        template_variants=(template,),
        optional_role_ids=('SL', 'SR'),
        include_baseline=True,
        created_at_utc=NOW,
    )
    rebuilt_topology = build_topology_search_spec(
        baseline=baseline,
        template_variants=(template,),
        optional_role_ids=('SR', 'SL'),
        include_baseline=True,
        created_at_utc='2026-09-19T00:00:30+00:00',
    )
    assert topology.topology_search_id == rebuilt_topology.topology_search_id
    assert topology.topology_search_sha256 == rebuilt_topology.topology_search_sha256
    assert topology.include_baseline
    assert [(item.kind, item.role_id, item.optional_role) for item in topology.options[0].operations] == [
        ('add', 'SL', True),
        ('add', 'SR', True),
    ]
    option_id = topology.options[0].option_id

    placements = (
        ProposedPlacementSpec(
            entity_id='sl',
            role_id='SL',
            zone_id='left-side-wall',
            allowed_region=_region(0.5, 1.4, 2.4, 3.4),
            exclusion_regions=(
                ProposedExclusionRegion(
                    region_id='blocked-mounting-strip',
                    vertices=_region(0.95, 1.2, 2.5, 3.3),
                ),
            ),
            min_z_m=1.2,
            max_z_m=1.4,
            xyz_axes=(
                CadSearchAxis(
                    entity_id='sl',
                    axis='x',
                    min_m=0.8,
                    max_m=1.0,
                    step_m=0.2,
                ),
                CadSearchAxis(
                    entity_id='sl',
                    axis='y',
                    min_m=2.8,
                    max_m=3.0,
                    step_m=0.2,
                ),
                CadSearchAxis(
                    entity_id='sl',
                    axis='z',
                    min_m=1.2,
                    max_m=1.4,
                    step_m=0.2,
                ),
            ),
            angle_axes=(
                PlacementAngleAxis(
                    parameter='aim_yaw_deg',
                    min_deg=-10.0,
                    max_deg=10.0,
                    step_deg=20.0,
                ),
                PlacementAngleAxis(
                    parameter='aim_pitch_deg',
                    min_deg=0.0,
                    max_deg=10.0,
                    step_deg=10.0,
                ),
            ),
        ),
        ProposedPlacementSpec(
            entity_id='sr',
            role_id='SR',
            zone_id='right-side-wall',
            allowed_region=_region(4.6, 5.5, 2.4, 3.4),
            min_z_m=1.2,
            max_z_m=1.4,
            angle_axes=(
                PlacementAngleAxis(
                    parameter='aim_yaw_deg',
                    min_deg=-10.0,
                    max_deg=10.0,
                    step_deg=20.0,
                ),
            ),
        ),
    )
    links = (
        LinkedPlacementRule(
            constraint_id='surround-mirror-x',
            master_entity_id='sl',
            slave_entity_id='sr',
            relation='mirror_x',
            mirror_axis_x_m=3.0,
        ),
        LinkedPlacementRule(
            constraint_id='surround-equal-y',
            master_entity_id='sl',
            slave_entity_id='sr',
            relation='equal_y',
        ),
        LinkedPlacementRule(
            constraint_id='surround-equal-z',
            master_entity_id='sl',
            slave_entity_id='sr',
            relation='equal_z',
        ),
    )
    constraints = CadConstraintSet(
        document_id=DOCUMENT_ID,
        constraints=(),
    )
    spec = build_topology_placement_search_spec(
        baseline=baseline,
        template_variant=template,
        topology_spec=topology,
        topology_option_id=option_id,
        placement_specs=placements,
        constraint_set=constraints,
        linked_rules=links,
        candidate_limit=200,
        created_at_utc=NOW,
    )
    rebuilt_spec = build_topology_placement_search_spec(
        baseline=baseline,
        template_variant=template,
        topology_spec=topology,
        topology_option_id=option_id,
        placement_specs=tuple(reversed(placements)),
        constraint_set=constraints,
        linked_rules=tuple(reversed(links)),
        candidate_limit=200,
        created_at_utc='2026-09-19T00:01:00+00:00',
    )
    assert rebuilt_spec.search_id == spec.search_id
    assert rebuilt_spec.search_sha256 == spec.search_sha256

    first = generate_topology_placement_candidates(
        baseline=baseline,
        template_variant=template,
        spec=spec,
        limit=100,
    )
    second = generate_topology_placement_candidates(
        baseline=baseline,
        template_variant=template,
        spec=spec,
        limit=100,
    )

    assert first.raw_candidate_count == 64
    assert first.feasible_candidate_count == 32
    assert first.rejected_candidate_count == 32
    assert first.duplicate_candidate_count == 0
    assert first.candidate_set_sha256 == second.candidate_set_sha256
    assert [item.candidate_id for item in first.candidates] == [
        item.candidate_id for item in second.candidates
    ]
    assert [item.candidate_sha256 for item in first.candidates] == [
        item.candidate_sha256 for item in second.candidates
    ]

    candidate = first.candidates[-1]
    assert candidate.positions['sr']['x_m'] == pytest.approx(
        6.0 - candidate.positions['sl']['x_m']
    )
    assert candidate.positions['sr']['y_m'] == pytest.approx(
        candidate.positions['sl']['y_m']
    )
    assert candidate.positions['sr']['z_m'] == pytest.approx(
        candidate.positions['sl']['z_m']
    )
    assert candidate.aim_yaw_deg == {'sl': 10.0, 'sr': 10.0}
    assert candidate.aim_pitch_deg == {'sl': 10.0}

    preview = topology_candidate_document(
        baseline=baseline,
        template_variant=template,
        spec=spec,
        candidate=candidate,
    )
    assert preview.entity('sl').speaker_role == 'SL'
    assert preview.entity('sr').speaker_role == 'SR'
    assert preview.entity('sl').position.x_m == pytest.approx(
        candidate.positions['sl']['x_m']
    )
    assert preview.entity('sr').position.x_m == pytest.approx(
        candidate.positions['sr']['x_m']
    )
    assert preview.entity('sl').aim_xyz is not None
    assert preview.entity('sl').aim_xyz.z > 0.0

    child = topology_candidate_to_system_variant(
        baseline=baseline,
        template_variant=template,
        spec=spec,
        candidate=candidate,
        created_at_utc='2026-09-19T00:02:00+00:00',
    )
    regenerated_child = topology_candidate_to_system_variant(
        baseline=baseline,
        template_variant=template,
        spec=spec,
        candidate=candidate,
        created_at_utc='2026-09-19T00:03:00+00:00',
    )
    assert child.variant_id == regenerated_child.variant_id
    assert child.variant_sha256 == regenerated_child.variant_sha256
    assert child.parent_variant_id == template.variant_id
    lifecycle = {item.entity_id: item for item in child.entity_lifecycle}
    assert lifecycle['sl'].state == 'proposed'
    assert lifecycle['sr'].state == 'proposed'
    assert lifecycle['sl'].measurement_ids == ()
    assert lifecycle['sr'].measurement_ids == ()

    topology_repository = CadTopologySearchRepository(variant_repository)
    topology_repository.save_topology_spec(topology)
    topology_repository.save_spec(spec)
    topology_repository.save_candidate_page(first)
    topology_repository.save_candidate_variant(candidate.candidate_id, child)
    assert topology_repository.get_topology_spec(topology.topology_search_id) == topology
    assert topology_repository.get_spec(spec.search_id) == spec
    assert topology_repository.get_candidate(candidate.candidate_id) == candidate
    assert topology_repository.variant_for_candidate(candidate.candidate_id) == child
    comparison = topology_repository.comparison_ref(candidate.candidate_id)
    assert comparison.variant_id == child.variant_id
    assert comparison.variant_sha256 == child.variant_sha256
    assert comparison.topology_search_id == topology.topology_search_id
    assert comparison.topology_option_id == option_id
    assert comparison.applied_revision_id is None

    # Search/persistence stays proposal-only: no temporary SceneRevision is created.
    assert baseline.document == before
    assert scene_repository.get(baseline.revision_id).document == before
    assert scene_repository.latest(DOCUMENT_ID).revision_id == baseline.revision_id

    tampered_positions = {
        entity_id: dict(position)
        for entity_id, position in candidate.positions.items()
    }
    tampered_positions['sl']['x_m'] += 0.01
    tampered = candidate.model_copy(update={'positions': tampered_positions})
    with pytest.raises(ValueError, match='identity mismatch'):
        topology_candidate_document(
            baseline=baseline,
            template_variant=template,
            spec=spec,
            candidate=tampered,
        )

    # A self-consistent hash is not enough: conversion must accept only an exact
    # member of the deterministic O10/O100B search grid.
    import htdt.cad_topology_search as topology_search

    forged_aim = dict(candidate.aim_yaw_deg)
    forged_aim['sl'] = 5.0
    forged_payload = candidate.identity_payload()
    forged_payload['aim_yaw_deg'] = forged_aim
    forged_sha = topology_search._digest(forged_payload)
    forged = candidate.model_copy(update={
        'aim_yaw_deg': forged_aim,
        'candidate_sha256': forged_sha,
        'candidate_id': 'tpc-' + forged_sha[:20],
    })
    with pytest.raises(ValueError, match='exact deterministic search member'):
        topology_candidate_document(
            baseline=baseline,
            template_variant=template,
            spec=spec,
            candidate=forged,
        )


def test_body_yaw_reuses_o80_oriented_allowed_region_rejection(
    tmp_path: Path,
) -> None:
    document_id = 'o100b-body-yaw-fixture'
    baseline_document = SceneDocument(
        document_id=document_id,
        room=RoomPrism(width_m=4.0, depth_m=4.0, height_m=2.4),
        entities=(
            _speaker('fl', 'FL', 1.0, 0.8, 1.0),
            _speaker('c', 'C', 2.0, 0.6, 0.9),
            _speaker('fr', 'FR', 3.0, 0.8, 1.0),
            _speaker('tfl', 'TFL', 1.4, 2.0, 2.2),
            _speaker('tfr', 'TFR', 2.6, 2.0, 2.2),
            SceneEntity(
                entity_id='mlp',
                kind='measurement_point',
                name='MLP',
                position=Position3(x_m=2.0, y_m=3.0, z_m=1.1),
            ),
        ),
    )
    scene_repository, baseline = _baseline(tmp_path, baseline_document)
    surround = ProposedEntitySpec(
        spec_id='proposal-sl',
        entity=_speaker(
            'sl',
            'SL',
            0.6,
            2.0,
            1.2,
            size=Size3(x_m=0.2, y_m=1.0, z_m=0.4),
        ),
        role_binding_id='SL',
    )
    template = build_system_variant(
        baseline=baseline,
        name='Proposed surround body-yaw template',
        role_bindings=(
            ChannelRoleBinding(role_id='FL', display_name='FL'),
            ChannelRoleBinding(role_id='C', display_name='C'),
            ChannelRoleBinding(role_id='FR', display_name='FR'),
            ChannelRoleBinding(role_id='TFL', display_name='TFL'),
            ChannelRoleBinding(role_id='TFR', display_name='TFR'),
            ChannelRoleBinding(role_id='SL', display_name='SL'),
        ),
        proposed_entities=(surround,),
        created_at_utc=NOW,
    )
    topology = build_topology_search_spec(
        baseline=baseline,
        template_variants=(template,),
        created_at_utc=NOW,
    )
    spec = build_topology_placement_search_spec(
        baseline=baseline,
        template_variant=template,
        topology_spec=topology,
        topology_option_id=topology.options[0].option_id,
        placement_specs=(
            ProposedPlacementSpec(
                entity_id='sl',
                role_id='SL',
                zone_id='narrow-left-zone',
                allowed_region=_region(0.4, 0.8, 1.3, 2.7),
                xyz_axes=(
                    CadSearchAxis(
                        entity_id='sl',
                        axis='x',
                        min_m=0.6,
                        max_m=0.6,
                        step_m=0.1,
                    ),
                ),
                angle_axes=(
                    PlacementAngleAxis(
                        parameter='body_yaw_deg',
                        min_deg=0.0,
                        max_deg=90.0,
                        step_deg=90.0,
                    ),
                ),
            ),
        ),
        constraint_set=CadConstraintSet(
            document_id=document_id,
            constraints=(),
        ),
        candidate_limit=10,
        created_at_utc=NOW,
    )

    page = generate_topology_placement_candidates(
        baseline=baseline,
        template_variant=template,
        spec=spec,
        limit=10,
    )

    assert page.raw_candidate_count == 2
    assert page.feasible_candidate_count == 1
    assert page.rejected_candidate_count == 1
    assert sum(page.rejection_counts.values()) == 1
    assert page.candidates[0].body_yaw_deg == {'sl': 0.0}
    assert scene_repository.latest(document_id).revision_id == baseline.revision_id


def test_topology_search_spec_reuses_o100a_add_remove_replace_diff(
    tmp_path: Path,
) -> None:
    _scene_repository, baseline = _baseline(tmp_path)
    replacement_fr = ProposedEntitySpec(
        spec_id='proposal-fr-replacement',
        entity=_speaker('fr', 'FR', 4.5, 1.0, 1.1),
        role_binding_id='FR',
    )
    surround = _proposal('sl', 'SL', 0.8)
    variant = build_system_variant(
        baseline=baseline,
        name='Explicit topology operations',
        role_bindings=(
            ChannelRoleBinding(role_id='FL', display_name='FL'),
            ChannelRoleBinding(role_id='FR', display_name='FR'),
            ChannelRoleBinding(role_id='TFL', display_name='TFL'),
            ChannelRoleBinding(role_id='TFR', display_name='TFR'),
            ChannelRoleBinding(role_id='SL', display_name='SL'),
        ),
        proposed_entities=(replacement_fr, surround),
        remove_entity_ids=('c',),
        created_at_utc=NOW,
    )

    topology = build_topology_search_spec(
        baseline=baseline,
        template_variants=(variant,),
        optional_role_ids=('SL',),
        include_baseline=True,
        created_at_utc=NOW,
    )

    assert [
        (
            operation.kind,
            operation.entity_id,
            operation.role_id,
            operation.optional_role,
        )
        for operation in topology.options[0].operations
    ] == [
        ('remove', 'c', 'C', False),
        ('replace', 'fr', 'FR', False),
        ('add', 'sl', 'SL', True),
    ]
