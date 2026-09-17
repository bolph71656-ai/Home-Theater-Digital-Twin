# N50 implementation progress

Tracking: #59  
Branch: `feat/n50-constraint-visualization`

## 2026-09-17 — implementation

- Confirmed `main` head `5dfd20aa6b7eec5d50e6f8ab94ba41db8fc79fb0` after N40 merge/status updates.
- Re-read N50 roadmap and A11 acceptance contract.
- Reviewed `placement_constraints.py`, `search_space.py`, `cad_scene.py`, and `cad_wall_models.py` before implementation.
- Reused the existing G10 placement engine unchanged as the feasibility authority.
- Added native immutable constraint models for allowed region, exclusion/walkway, wall clearance, and pair distance.
- Added `CadConstraintRepository` as a document-scoped authoring workspace beside scene storage in the same SQLite file.
- Added pure CAD→G10 adapter and typed CAD evaluation results with Japanese reason codes/text.
- Stable wall constraints persist N30b `wall_id`; transient G10 `from_vertex_id->to_vertex_id` edge IDs are generated only at evaluation time.
- Physical rectangular entities use a conservative circumscribed horizontal radius for the existing G10 envelope model; the UI does not describe this as exact mesh collision.
- Added focused tests for coordinate/profile mapping, stable wall mapping after split topology, wall/walkway reason mapping, position override immutability, unknown-wall rejection, workspace round-trip, candidate blocking policy, and hide/lock feasibility independence.
- Added `ConstraintEditorWindow` on top of the accepted N40 workflow. Normal launcher `htdt.native_cad` now uses this product composition.
- Added Japanese-first `制約` dock with current status, violation list, actual/required detail, authoring buttons, and explicit non-quality wording.
- Added viewport region patterns, selected entity/counterpart highlighting, selected wall line, rejected-candidate marker, and distance segment.
- Integrated candidate evaluation into the existing move preview path. No second transform engine was added.
- Commit policy blocks newly introduced hard violations and worsened scalar-distance violations, while allowing recovery motion from an already-existing region violation.
- Rejected move restores the committed pose, does not grow history, and preserves rejection evidence for inspection.
- Entity deletion and ambiguous wall split/merge/delete are blocked while referenced by full N50 constraints. Full wall-clearance constraints are not guessed across topology changes; users must explicitly remove/redefine them.
- `feasible` is shown only as placement-constraint satisfaction (`制約を満たす / 制約違反`). It is not surfaced as acoustic quality, recommendation, ranking, or score.
- Browser UI remains frozen.
- RDC has not been used for N50 and remains reserved for the final A11 Windows gate.

## Verification completed before A11 hardware gate

- Domain slice CI #230: PASS.
- Product UI / commit-policy CI #235: PASS, including backend tests, native launcher CLI, existing acceptance harness compilation, PowerShell syntax, frontend build, and smoke test.
- Added `scripts/validate_n50_windows.py` for A11 and added it to CI compile coverage.
- A11 fixture starts fully feasible, then uses real OS mouse input to create a right-wall-clearance violation and a walkway violation, selects each reason with the real mouse, checks actual/required and viewport evidence, and verifies normal editing still works after rejection.
- A11 also checks persisted constraint workspace equality and rejects acoustic-quality wording.

## Persistence boundary

N50 constraint definitions are document-scoped authoring state, persisted beside `SceneRepository`, not embedded in `SceneRevision`. This follows the existing G10 Context/ConstraintSet separation and avoids silently changing the established scene hash contract for N50. Future N60/N70 jobs must capture an immutable constraint-workspace hash/snapshot together with the exact SceneRevision at submission time; mutable latest workspace state must never replace captured job input.

## Remaining gate

1. Wait for the latest CI run containing the A11 harness and hide/lock invariant test to complete.
2. If green, run A11 once on the owned Windows 11 PC using real mouse input; bundle clean-worktree and environment checks in the same RDC session.
3. Fix only failures observed by that acceptance run, then re-run the meaningful affected gate.
4. Record A11 environment/results and any first-use friction in `docs/N50_ACCEPTANCE_2026-09-17.md`.
5. Update `docs/IMPLEMENTATION_STATUS.md`, mark PR #60 ready, merge, close #59, and advance the roadmap/status to N60.

## Known intentional limits

- N50 does not provide constraint-definition Undo/history; constraint authoring is explicit and persists immediately to the workspace.
- N50 does not automatically migrate full wall-clearance semantics across split/merge because the intended successor scope is ambiguous.
- G10 footprint constraints use a conservative radial envelope rather than oriented-box collision.
- Optimization/ranking remains a later milestone; N50 only exposes placement feasibility and reasons.
