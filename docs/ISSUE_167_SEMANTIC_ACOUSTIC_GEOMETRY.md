# Issue #167 — semantic acoustic geometry conversion slice

Date: 2026-09-19

## Scope implemented

This slice starts from the raw visual mesh authority merged by PR #195 and adds an explicit, versioned R120 semantic conversion path without reimplementing OBJ/GLB ingestion.

Implemented:

- immutable/versioned `SemanticGeometryConversionProfile`
- deterministic `SemanticGeometryConversionRequest` bound to:
  - exact `RawVisualMesh.mesh_id`
  - exact raw mesh semantic hash
  - exact original asset SHA-256
  - exact PR #195 diagnostic identity/hash
  - exact source SceneRevision id when a parent revision exists
- explicit guided repair actions:
  - remove triangle
  - flip triangle
  - add triangle
  - set vertex with expected-before stale guard
- deterministic repair operation ids and immutable before/after topology-hash lineage
- stable raw-triangle lineage ids and stable semantic-surface ids
- explicit surface classification:
  - `room_boundary`
  - `object_surface`
  - `unknown`
- unassigned triangles remain an explicit `unknown` surface; they are never mapped to a default wall/material
- post-repair conversion diagnostics by reusing the PR #195 diagnostic implementation over an in-memory derived view
- explicit unresolved-condition list and guided repair suggestions; suggestions never execute automatically
- R120 geometry compiler-contract readiness:
  - `blocked_by_geometry`
  - `blocked_by_surface_semantics`
  - `ready_for_r120_geometry_compiler_contract`
- deterministic semantic geometry identity/hash and canonical serialization/reopen
- SceneDocument schema v4 optional `r120_semantic_geometry` field
- exact SceneRevision binding metadata in `cad_r120_semantic_geometry_bindings`
- save/reopen validation that the persisted binding matches the semantic geometry stored inside the exact SceneRevision payload

## Authority boundary

The persistent geometry truth remains the SceneRevision/R120 payload. The binding table contains only exact identity/provenance references; it does not store a second copy of geometry.

`RawVisualMesh` remains immutable. Repair actions create a derived semantic geometry and never rewrite original asset bytes or the PR #195 raw snapshot.

This slice does not infer:

- acoustic material assignment
- AcousticRegion
- Portal
- BoundaryTermination

The conversion profile records material authority as externally required downstream. A clean mesh is still blocked from the R120 geometry compiler contract until every triangle has an explicit non-`unknown` semantic surface classification.

`solver_ready` remains false in this slice. `ready_for_r120_geometry_compiler_contract` means only that the semantic geometry contract is admissible for a future R120 compiler; it does not claim that material/boundary physics or a compiled solver representation exists.

## Compatibility

Existing SceneRevision hashes remain unchanged when `r120_semantic_geometry` is absent. No R100B solver adapter is changed. No wave/ray compiler implementation is added.

The binding table uses the existing native repository after the native schema compatibility gate and stores no geometry payload.

## Focused acceptance coverage

`backend/tests/test_semantic_geometry.py` covers:

1. PR #195 representative imperfect OBJ fixture
2. exact raw-byte immutability
3. explicit duplicate-triangle repair
4. deterministic repair lineage and semantic output identity
5. unresolved geometry blocks compiler-contract readiness
6. clean closed geometry with no semantic assignment remains blocked
7. explicit room-boundary assignment reaches only the R120 geometry compiler contract (not solver-ready)
8. semantic geometry serialization/reopen identity
9. exact source SceneRevision binding
10. save/reopen through `SceneRepository` with the same semantic geometry result and binding metadata

## Deferred

Deferred from this slice:

- material-definition authority / material assignment workflow
- AcousticRegion / Portal / BoundaryTermination authoring
- semantic surface editor/UI
- generalized automatic topology repair
- GA ray-leak / portal diagnostics
- R120 wave compiler
- R120 ray compiler
- compiler approximation/error metadata
- R100B adapter changes
- solver-ready compiled representations

These remain explicit follow-on work under #167/#101; no unsupported condition is silently promoted.
