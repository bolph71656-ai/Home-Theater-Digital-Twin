# N80 implementation progress

Tracking: Issue #65  
Branch: `feat/n80-optimization-workspace`  
Base main: `286f3b86a742ef6e3454d91c609ce1f84d840c57`

## 2026-09-18 — start

- N70 merged as `2ca8755b66af5521c2ed4fc98d39ce1aeb732c64`.
- N70 post-merge status sync main head is `286f3b86a742ef6e3454d91c609ce1f84d840c57`.
- CI #315 / run `35277173472` passed completely on that main head.
- Created Issue #65 and branch `feat/n80-optimization-workspace` from the green main head.

## Existing implementation findings

### O10 is already implemented

`backend/src/htdt/search_space.py` already provides:

- `search-space-grid-1` deterministic decimal grids;
- pre-generation raw candidate limits;
- hard-constraint filtering through G10;
- deterministic candidate IDs;
- raw / feasible / rejected / duplicate counts;
- deterministic `candidate_set_sha256`;
- paged candidate coordinates;
- no prediction, ranking, objective or Pareto semantics.

N80 will reuse this engine rather than reimplement it.

### Native N50 adapter is reusable

`backend/src/htdt/cad_constraints.py` already projects an exact native SceneDocument into the transient G10 Context-shaped algorithm input and builds the G10 constraint request. This adapter boundary lets N80 preserve native SceneRevision authority while reusing the existing O10 engine.

### Candidate apply infrastructure already exists

`backend/src/htdt/cad_document.py` already has `TransformEntitiesCommand`, which replaces multiple exact SceneEntity objects as one history command. N80a can use the same command semantics for candidate apply and guarantee one Undo restores all candidate-touched positions.

### Pareto/objective implementation is not present

Repository inspection found no existing O30 objective-vector / O40 Pareto implementation. N80 will not build a cosmetic Pareto UI before those algorithms exist. N80a is therefore restricted to SearchSpec authority, deterministic candidate generation, preview and explicit apply.

## N80a plan

1. Add immutable native SearchSpec model/repository beside the native scene database.
2. Bind SearchSpec to exact source SceneRevision/content hash and canonical native constraint-workspace hash.
3. Add native-to-O10 adapter using existing `scene_to_g10_context()` / G10 request generation.
4. Keep candidates derived/paged instead of persisting thousands of rows.
5. Add WorkingDocument candidate-position apply as one `TransformEntitiesCommand`.
6. Add Japanese native `最適化` workspace over N70.
7. Reuse N70 bulk marker cloud for candidate visualization.
8. Add focused tests only for immutable binding, deterministic regeneration, stale rejection and one-command apply/Undo.
9. Reserve RDC for final A13/A14 real-Windows acceptance after CI is green.

Detailed contract: [N80 design](N80_DESIGN.md).

## Authority decisions

- Native `SceneRevision` is the source authority.
- Native `CadConstraintSet` is the constraint authority.
- Legacy Context-shaped payloads are transient algorithm adapters only.
- Legacy `Store.search_specs` is not reused as native persistence authority.
- Candidate feasibility is not a quality score.
- Search candidates are not labeled recommended/optimal.
- External or scalar-field prediction remains model-gated exactly as in N70.
