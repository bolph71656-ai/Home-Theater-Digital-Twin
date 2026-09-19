from __future__ import annotations

from copy import deepcopy

from htdt.cad_repository import SceneRevision
from htdt.cad_scene import SceneDocument, scene_content_hash
from htdt.r120_geometry_compiler import (
    AcousticRegionDeclaration,
    ExactExternalAuthorityRef,
    LeakDiagnosticSample,
    PortalBoundaryEdge,
    PortalDeclaration,
    R120GeometryCompilationError,
    SurfaceBoundaryAuthorityBinding,
    compile_r120_geometry,
    deserialize_r120_compiled_geometry,
    deserialize_r120_leak_portal_diagnostic,
    diagnose_r120_leak_and_portals,
    make_acoustic_region_authority,
    make_leak_portal_diagnostic_request,
    make_leak_sampling_authority,
    make_portal_authority,
    make_r120_geometry_compilation_request,
    serialize_r120_compiled_geometry,
    serialize_r120_leak_portal_diagnostic,
)
from htdt.raw_mesh import import_raw_visual_mesh
from htdt.semantic_geometry import (
    RemoveTriangleRepair,
    SurfaceSemanticAssignment,
    convert_raw_visual_mesh_to_semantic_geometry,
    explicit_identity_source_to_scene_transform,
    make_semantic_geometry_conversion_request,
    raw_triangle_ids,
)


CLOSED_TETRA = b'''\
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
f 1 3 2
f 1 2 4
f 1 4 3
f 2 3 4
'''

TWO_TETRA_WITH_TINY_SECOND = b'''\
v 0 0 0
v 1 0 0
v 0 1 0
v 0 0 1
f 1 3 2
f 1 2 4
f 1 4 3
f 2 3 4
v 2 0 0
v 2.0001 0 0
v 2 0.0001 0
v 2 0 0.0001
f 5 7 6
f 5 6 8
f 5 8 7
f 6 7 8
'''


def _revision(
    asset: bytes = CLOSED_TETRA,
    *,
    assign_semantics: bool = True,
    remove_triangle_index: int | None = None,
    revision_id: str = 'scene-r120-fixture',
) -> tuple[SceneRevision, object]:
    mesh = import_raw_visual_mesh(asset, source_name='r120-fixture.obj')
    triangle_ids = raw_triangle_ids(mesh)
    repairs = ()
    retained = triangle_ids
    if remove_triangle_index is not None:
        removed = triangle_ids[remove_triangle_index]
        repairs = (
            RemoveTriangleRepair(
                triangle_id=removed,
                reason='fixture explicitly removes one face to create an unresolved opening',
            ),
        )
        retained = tuple(item for item in triangle_ids if item != removed)

    assignments = ()
    if assign_semantics:
        assignments = (
            SurfaceSemanticAssignment(
                surface_key='room-shell',
                triangle_ids=retained,
                semantic_class='room_boundary',
            ),
        )
    request = make_semantic_geometry_conversion_request(
        mesh,
        source_scene_revision_id=None,
        source_to_scene_transform=explicit_identity_source_to_scene_transform(
            reason='fixture OBJ coordinates are explicitly HTDT metres',
        ),
        repairs=repairs,
        surface_assignments=assignments,
    )
    geometry = convert_raw_visual_mesh_to_semantic_geometry(mesh, request)
    document = SceneDocument(
        document_id='r120-compiler-fixture',
        schema_version=4,
        room=None,
        r120_semantic_geometry=geometry,
        entities=(),
    )
    revision = SceneRevision(
        revision_id=revision_id,
        document_id=document.document_id,
        parent_revision_id=None,
        created_at_utc='2026-09-19T00:00:00+00:00',
        content_hash=scene_content_hash(document),
        document=document,
    )
    return revision, mesh


def _compile(
    revision: SceneRevision,
    *,
    input_policy: str = 'require_contract_ready',
    tolerance: float = 1.0e-6,
    approximation_policy: str = 'none',
    tiny_feature_policy: str = 'preserve',
    **kwargs,
):
    request = make_r120_geometry_compilation_request(
        revision,
        geometric_tolerance_m=tolerance,
        input_policy=input_policy,
        approximation_policy=approximation_policy,
        tiny_feature_policy=tiny_feature_policy,
    )
    return compile_r120_geometry(revision, request, **kwargs)


def _sampling():
    return make_leak_sampling_authority(
        (
            LeakDiagnosticSample(
                sample_id='toward-z0-opening',
                origin_m=(0.1, 0.1, 0.1),
                direction_unit=(0.0, 0.0, -1.0),
            ),
        )
    )


def _surface_id(revision: SceneRevision) -> str:
    geometry = revision.document.r120_semantic_geometry
    assert geometry is not None
    return geometry.surfaces[0].surface_id


def _dummy_external_ref(name: str) -> ExactExternalAuthorityRef:
    return ExactExternalAuthorityRef(
        authority_id=name,
        authority_version='fixture-v1',
        semantic_hash_sha256='a' * 64,
    )


def test_compiler_contract_preserves_exact_scene_geometry_and_surface_mapping() -> None:
    revision, _ = _revision()
    geometry = revision.document.r120_semantic_geometry
    assert geometry is not None
    assert geometry.geometry_compiler_readiness == 'ready_for_r120_geometry_compiler_contract'
    assert geometry.solver_ready is False

    compiled = _compile(revision)

    assert compiled.exact_scene_revision_id == revision.revision_id
    assert compiled.exact_scene_revision_content_hash == revision.content_hash
    assert compiled.exact_semantic_geometry_id == geometry.geometry_id
    assert compiled.exact_semantic_geometry_hash_sha256 == geometry.semantic_hash_sha256
    assert compiled.request.compiler_id == 'htdt.r120.solver_neutral_geometry_compiler'
    assert compiled.request.compiler_version == '1'
    assert compiled.request.target_representation == 'indexed_triangle_surface_v1'
    assert compiled.request.coordinate_convention == 'htdt-x-right-y-rear-z-up'
    assert compiled.request.unit_convention == 'metre'
    assert compiled.closed_shell_diagnostics.closed_shell is True
    assert compiled.closed_shell_diagnostics.boundary_edge_count == 0
    assert compiled.closed_shell_diagnostics.enclosed_volume_m3 == 1.0 / 6.0
    assert len(compiled.surface_mapping) == 1
    assert compiled.surface_mapping[0].source_surface_id == geometry.surfaces[0].surface_id
    assert compiled.surface_mapping[0].source_triangle_ids == geometry.surfaces[0].triangle_ids
    assert compiled.surface_mapping[0].compiled_triangle_indices == (0, 1, 2, 3)
    assert compiled.readiness.geometry_compiled is True
    assert compiled.readiness.wave_geometry_ready is False
    assert compiled.readiness.geometric_acoustics_geometry_ready is False
    assert compiled.readiness.material_assignment_missing is True
    assert compiled.readiness.region_definition_missing is True
    assert compiled.readiness.portal_definition_missing is True
    assert compiled.readiness.boundary_physics_missing is True


def test_exact_external_authorities_can_complete_closed_geometry_readiness_without_invented_materials() -> None:
    revision, _ = _revision()
    surface_id = _surface_id(revision)
    region = make_acoustic_region_authority(
        (
            AcousticRegionDeclaration(
                region_id='room-air',
                boundary_surface_ids=(surface_id,),
            ),
        )
    )
    portals = make_portal_authority(declaration_mode='explicit_none')
    bindings = (
        SurfaceBoundaryAuthorityBinding(
            source_surface_id=surface_id,
            material_authority=_dummy_external_ref('fixture-material'),
            boundary_physics_authority=_dummy_external_ref('fixture-boundary-physics'),
        ),
    )

    compiled = _compile(
        revision,
        surface_boundary_bindings=bindings,
        region_authority=region,
        portal_authority=portals,
    )

    assert compiled.readiness.material_assignment_missing is False
    assert compiled.readiness.region_definition_missing is False
    assert compiled.readiness.portal_definition_missing is False
    assert compiled.readiness.boundary_physics_missing is False
    assert compiled.readiness.wave_geometry_ready is True
    assert compiled.readiness.geometric_acoustics_geometry_ready is True
    assert compiled.surface_mapping[0].material_authority == bindings[0].material_authority
    assert compiled.surface_mapping[0].boundary_physics_authority == bindings[0].boundary_physics_authority


def test_unresolved_semantic_geometry_is_blocked_normally_but_can_compile_for_diagnostics() -> None:
    revision, _ = _revision(remove_triangle_index=0)
    geometry = revision.document.r120_semantic_geometry
    assert geometry is not None
    assert geometry.geometry_compiler_readiness == 'blocked_by_geometry'

    request = make_r120_geometry_compilation_request(
        revision,
        geometric_tolerance_m=1.0e-6,
    )
    try:
        compile_r120_geometry(revision, request)
    except R120GeometryCompilationError as exc:
        assert 'not ready_for_r120_geometry_compiler_contract' in str(exc)
    else:
        raise AssertionError('unresolved semantic geometry must fail normal compilation')

    compiled = _compile(revision, input_policy='diagnostic_compile_unresolved')
    assert compiled.readiness.geometry_compiled is True
    assert compiled.readiness.wave_geometry_ready is False
    assert 'input_semantic_geometry_not_compiler_contract_ready' in compiled.unresolved_conditions
    assert compiled.closed_shell_diagnostics.closed_shell is False
    assert compiled.closed_shell_diagnostics.boundary_edge_count == 3


def test_unknown_semantic_surface_stays_explicitly_blocked() -> None:
    revision, _ = _revision(assign_semantics=False)
    geometry = revision.document.r120_semantic_geometry
    assert geometry is not None
    assert geometry.geometry_compiler_readiness == 'blocked_by_surface_semantics'
    assert geometry.surfaces[0].semantic_class == 'unknown'

    compiled = _compile(revision, input_policy='diagnostic_compile_unresolved')

    assert compiled.surface_mapping[0].source_surface_id == geometry.surfaces[0].surface_id
    assert compiled.surface_mapping[0].semantic_class == 'unknown'
    assert 'unknown_semantic_surface' in compiled.unresolved_conditions
    assert compiled.readiness.wave_geometry_ready is False


def test_unintended_opening_is_distinct_from_explicit_portal_and_has_deterministic_ray_evidence() -> None:
    revision, _ = _revision(remove_triangle_index=0)
    compiled = _compile(revision, input_policy='diagnostic_compile_unresolved')
    portals = make_portal_authority(declaration_mode='explicit_none')
    request = make_leak_portal_diagnostic_request(
        compiled,
        closed_boundary_expectation=True,
        sampling_authority=_sampling(),
    )

    result = diagnose_r120_leak_and_portals(compiled, request, portal_authority=portals)

    codes = {finding.code for finding in result.findings}
    assert 'unintended_geometric_opening' in codes
    assert 'unintended_ray_escape' in codes
    assert 'explicit_portal_opening' not in codes
    assert len(result.unintended_boundary_edges) == 3
    assert result.explicit_portal_boundary_edges == ()
    assert result.ray_escape_evidence[0].escaped_without_intersection is True
    assert result.ray_escape_evidence[0].positive_intersection_count == 0
    assert 'unintended_geometric_opening' in result.unresolved_conditions


def test_explicit_portal_matches_opening_without_auto_repair() -> None:
    revision, _ = _revision(remove_triangle_index=0)
    geometry_before = deepcopy(revision.document.r120_semantic_geometry.model_dump(mode='json'))
    compiled = _compile(revision, input_policy='diagnostic_compile_unresolved')
    surface_id = _surface_id(revision)
    portal_edges = (
        PortalBoundaryEdge(source_surface_id=surface_id, vertex_a=0, vertex_b=1),
        PortalBoundaryEdge(source_surface_id=surface_id, vertex_a=0, vertex_b=2),
        PortalBoundaryEdge(source_surface_id=surface_id, vertex_a=1, vertex_b=2),
    )
    portals = make_portal_authority(
        declaration_mode='explicit_list',
        declarations=(
            PortalDeclaration(
                portal_id='front-opening',
                region_ids=('room-air',),
                boundary_edges=portal_edges,
            ),
        ),
    )
    request = make_leak_portal_diagnostic_request(
        compiled,
        closed_boundary_expectation=True,
        sampling_authority=_sampling(),
    )

    result = diagnose_r120_leak_and_portals(compiled, request, portal_authority=portals)

    codes = {finding.code for finding in result.findings}
    assert 'explicit_portal_opening' in codes
    assert 'explicit_portal_ray_escape' in codes
    assert 'unintended_geometric_opening' not in codes
    assert result.unintended_boundary_edges == ()
    assert len(result.explicit_portal_boundary_edges) == 3
    assert result.portal_declaration_mismatch_edges == ()
    assert result.unresolved_conditions == ()
    assert revision.document.r120_semantic_geometry.model_dump(mode='json') == geometry_before


def test_portal_declaration_mismatch_is_fail_closed() -> None:
    revision, _ = _revision(remove_triangle_index=0)
    compiled = _compile(revision, input_policy='diagnostic_compile_unresolved')
    surface_id = _surface_id(revision)
    portals = make_portal_authority(
        declaration_mode='explicit_list',
        declarations=(
            PortalDeclaration(
                portal_id='mismatched-opening',
                region_ids=('room-air',),
                boundary_edges=(
                    PortalBoundaryEdge(
                        source_surface_id=surface_id,
                        vertex_a=0,
                        vertex_b=3,
                    ),
                ),
            ),
        ),
    )
    request = make_leak_portal_diagnostic_request(
        compiled,
        closed_boundary_expectation=True,
        sampling_authority=_sampling(),
    )

    result = diagnose_r120_leak_and_portals(compiled, request, portal_authority=portals)

    codes = {finding.code for finding in result.findings}
    assert 'portal_boundary_mismatch' in codes
    assert 'unintended_geometric_opening' in codes
    assert result.portal_declaration_mismatch_edges
    assert 'portal_boundary_mismatch' in result.unresolved_conditions


def test_approximation_policy_records_every_dropped_feature_and_preserves_surface_identity() -> None:
    revision, _ = _revision(TWO_TETRA_WITH_TINY_SECOND)
    geometry = revision.document.r120_semantic_geometry
    assert geometry is not None
    before = deepcopy(geometry.model_dump(mode='json'))

    compiled = _compile(
        revision,
        input_policy='diagnostic_compile_unresolved',
        tolerance=0.001,
        approximation_policy='explicit_policy_only',
        tiny_feature_policy='drop_below_tolerance',
    )

    assert len(compiled.approximation_operations) == 4
    assert len(compiled.dropped_features) == 4
    assert compiled.maximum_recorded_approximation_error_m > 0.0
    assert all(item.tolerance_m == 0.001 for item in compiled.approximation_operations)
    assert compiled.surface_mapping[0].source_surface_id == geometry.surfaces[0].surface_id
    assert len(compiled.surface_mapping[0].source_triangle_ids) == 8
    assert len(compiled.surface_mapping[0].compiled_triangle_indices) == 4
    assert len(compiled.surface_mapping[0].dropped_source_triangle_ids) == 4
    assert geometry.model_dump(mode='json') == before


def test_same_input_and_settings_have_same_compiled_hash_and_round_trip_exactly() -> None:
    revision, _ = _revision()
    request_a = make_r120_geometry_compilation_request(
        revision,
        geometric_tolerance_m=1.0e-6,
    )
    request_b = make_r120_geometry_compilation_request(
        revision,
        geometric_tolerance_m=1.0e-6,
    )
    compiled_a = compile_r120_geometry(revision, request_a)
    compiled_b = compile_r120_geometry(revision, request_b)

    assert request_a == request_b
    assert request_a.request_semantic_hash_sha256 == request_b.request_semantic_hash_sha256
    assert compiled_a.compiled_hash_sha256 == compiled_b.compiled_hash_sha256
    assert compiled_a.compiled_geometry_id == compiled_b.compiled_geometry_id
    assert compiled_a.topology_identity_sha256 == compiled_b.topology_identity_sha256

    reopened = deserialize_r120_compiled_geometry(serialize_r120_compiled_geometry(compiled_a))
    assert reopened == compiled_a
    assert reopened.compiled_hash_sha256 == compiled_a.compiled_hash_sha256
    assert reopened.exact_scene_revision_content_hash == revision.content_hash


def test_leak_diagnostic_round_trip_preserves_exact_compiled_input_hash() -> None:
    revision, _ = _revision(remove_triangle_index=0)
    compiled = _compile(revision, input_policy='diagnostic_compile_unresolved')
    request = make_leak_portal_diagnostic_request(
        compiled,
        closed_boundary_expectation=True,
        sampling_authority=_sampling(),
    )
    result = diagnose_r120_leak_and_portals(
        compiled,
        request,
        portal_authority=make_portal_authority(declaration_mode='explicit_none'),
    )

    reopened = deserialize_r120_leak_portal_diagnostic(
        serialize_r120_leak_portal_diagnostic(result)
    )

    assert reopened == result
    assert reopened.exact_compiled_geometry_id == compiled.compiled_geometry_id
    assert reopened.exact_compiled_geometry_hash_sha256 == compiled.compiled_hash_sha256
    assert reopened.request.sampling_authority == request.sampling_authority
    assert reopened.diagnostic_hash_sha256 == result.diagnostic_hash_sha256
