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

## 2026-09-18 — N80a owned-Windows acceptance

- Last product-code head: `c6cc15e76edbc1ac263911ee084803ca1e32b42c`.
- Product CI #321 / run `35280237062`: PASS.
- Gate-only head: `ff4dc8078eb9ca0b3effaed66b523cff175fea1a`.
- Final gate CI #323 / run `35280664154`: PASS.
- A13: stale revision, UI responsiveness, explicit cancel, document switch, and clean close/no-worker all PASS on owned Windows at 200% DPI.
- A14: SearchSpec creation, deterministic candidate generation, real-mouse candidate selection, non-authoritative preview, one-command apply, and one-Undo exact restoration all PASS.
- Hardware gate result: `N80_HARDWARE_GATE_RESULT=PASS`.
- Local checkout restored to `5ede848e8e0b0967a50c04c83ff679a649ca439b` with post-status count `0`.
- Detailed record: [N80a Windows acceptance](N80A_ACCEPTANCE_2026-09-18.md).

N80a is accepted and merged through PR #66 as `7473bb3efdbc511369c9a023b0b210eb5cde3553`. Issue #65 remains open: O20 requires a verified model contract, and O30/O40 objective/Pareto algorithms are not yet implemented.


## 2026-09-18 — O30/O40 core started (PR #70)

Branch `feat/n80-objectives-pareto` / draft PR #70 starts the algorithm-only part of N80b/c without bypassing the O20 model gate.

Commit `88f8a348a211789a2d0f5d50278853eddcbf42e6` added:

- frozen `ObjectiveMetric` / `ObjectiveVector` models with explicit minimize direction;
- explicit response evaluation band/reference band/excluded bands;
- target-response level RMS, peak excess, dip deficit and optional level-aligned shape RMS;
- pair/left-right response difference metrics;
- multi-seat pairwise difference metrics;
- total/max physical movement objectives;
- deterministic `pareto-front-1` dominance and non-dominated extraction;
- focused synthetic tests for metric separation, movement math, known Pareto fronts, equal vectors, missing objectives and duplicate candidate rejection.

Commit `0e01bd9b75c4f7886d1cc1730bafa1cd5db973fa` refined multi-seat evaluation so level-sensitive difference and level-aligned shape difference remain separate objectives rather than selecting one or the other.

O20 batch prediction is still intentionally not connected. N70 currently exposes validated geometry candidates, not a validated FR/SPL predictor suitable for batch optimization. O30/O40 pure algorithms can be verified independently with synthetic data while preserving that boundary.

No RDC is required for this algorithm-only slice. Windows real-interaction testing remains reserved for later native persistence/UI integration.


## 2026-09-18 — O30/O40 native persistence

Commit `0bbec7295936b5cf7154a14f839e1004df4039dc` added immutable native persistence for objective vectors and Pareto sets:

- each `CadObjectiveEvaluation` binds to exact document / SceneRevision / scene content hash / SearchSpec ID+SHA / candidate ID;
- evaluation spec is canonical JSON + SHA-256;
- evidence references preserve explicit `measured / derived / predicted / hypothesis` classification and source identity;
- each stored vector keeps its independent objective IDs/units/direction;
- each `CadParetoSet` stores exact objective IDs plus referenced evaluation IDs/hashes/candidate IDs;
- Pareto save re-loads all referenced immutable evaluations and recomputes the front; a mismatched/tampered Pareto result is rejected;
- native SceneRevision/SearchSpec binding mismatch is rejected before persistence.

Commit `02965d0136a330a2ef0bad2733698a22a8665e91` canonicalized evidence-ref ordering so equivalent input-reference sets produce the same evaluation identity regardless of caller ordering.

The first persistence CI exposed only a test-fixture defect: the new physical speaker fixture omitted mandatory `size_m`. Commit `911b44c647c65c53c94febf6033432dc1b0927ae` fixed the fixture using the same physical speaker dimensions as the accepted N80a tests.

CI #335 / run `35288664125` passed completely on `911b44c647c65c53c94febf6033432dc1b0927ae`, including backend tests, native launcher checks, Windows acceptance-harness compile, N60/N70/N80 gate preflights, frontend build and smoke test.

This slice is algorithm/persistence only. It does not require a new real-Windows interaction gate and does not close Issue #65. O20 batch prediction and later native Pareto UI/measurement loop remain separate work.


## 2026-09-18 — O20 transactional REW Room Simulator batch (PR #71)

PR #70 merged to main as `b4381f4b01683bba65b3857514ea583160f0eb7b`. Issue #65 remains open.

Branch `feat/n80-o20-rew-roomsim-batch` / draft PR #71 starts O20 using the already validated REW Room Simulator contract rather than inventing a new predictor.

Implemented so far:

- `rew_roomsim_batch.py`: explicit write-capable control subclass separated from the ordinary GET-only adapter;
- documented Room Simulator POST routes for head/source position only;
- full-state pre/apply/post-response/restore hashing;
- exact native room dimension and active-source coverage checks before prediction;
- fail-closed handling for concurrent REW/user state changes;
- restore of write-induced position side effects such as coupled source movement;
- no result return unless restore is exact;
- exact REW version and batch adapter version in the returned model provenance;
- `cad_roomsim.py`: native SceneRevision/SearchSpec/Candidate -> Room Simulator request adapter;
- exact shifted-rectangle local-coordinate conversion;
- explicit acoustic-reference semantics;
- rejection of non-rectangular rooms, unbound moved speakers and speakers with unknown acoustic reference.

The product does not modify Room Simulator room dimensions, absorptions, options or source configuration in this slice.

Focused tests use fake transport/state and cover success, dimension/source mismatch, documented POST routes, external change, restore failure, coupled-source side effects, shifted rectangles, acoustic-reference offsets and L-room rejection.

The existing 2026-09-16 owned-PC probe already established that beta135 can change the head by 1 cm, produce a changed FR, then restore state and raw FR exactly. PR #71 first converts that observation into a fail-closed production transaction contract. A new RDC write gate will be deferred until CI and the later native batch/persistence integration are complete, so real-machine calls stay minimal.


## 2026-09-18 — O20 transaction accepted; immutable result slice started

PR #71 was accepted after CI #345 / run `35289874654` passed completely and merged to main as `cdbd0f45f8c66b01522fcc3006b8019e2cd1ba88`.

The initial CI #344 failure was a representation bug in expected derived HTDT coordinates plus an overly broad restore-error classification. Commit `fb1ba7a90c15810a01284a68dab9245679fab347` fixed both without widening REW write authority. PR #68 was then closed unmerged as superseded by the narrower position-only contract.

Current branch `feat/n80-o20-result-persistence` continues Issue #67 with the next O20 slice:

- immutable batch specs bound to exact SceneRevision/SearchSpec/candidate-set hash;
- candidate requests frozen before any REW write;
- append-only completed/failed candidate attempts;
- exact REW/state/FR provenance for completed attempts;
- failure records never publish an FR;
- resume skips completed candidates and retries failed candidates using a new immutable attempt index;
- cancellation is checked between candidates so the active transaction always completes its restore path;
- any candidate failure halts that invocation instead of continuing writes blindly;
- completed attempt FR can be converted to the existing O30 `FrequencyResponse` input without changing its evidence class.

Focused tests cover cancel→resume, failed-attempt retry, authority binding, exact request freezing and exact Room Simulator state restoration. No RDC is used in this slice before CI is green; the writable owned-Windows gate remains consolidated with the later native integration.
