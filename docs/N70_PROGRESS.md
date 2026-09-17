# N70 implementation progress

Tracking: Issue #63  
PR: #64  
Branch: `feat/n70-prediction-visualization`  
Base main: `86354dd58200738b33ae27261a5308e3551bcbac`

## 2026-09-17 — start

- N60 merged as `f1694eb879a250835efa026ac5dacdec18362788`; Issue #61 closed `completed`.
- Post-merge status/acceptance docs were synchronized on main as `86354dd58200738b33ae27261a5308e3551bcbac`.
- Created Issue #63 and branch `feat/n70-prediction-visualization` from that main head.
- Re-read `IMPLEMENTATION_ROADMAP.md`, `CAD_EDITOR_ACCEPTANCE.md`, `PLACEMENT_OPTIMIZATION_ROADMAP.md`, `DATA_AND_ANALYSIS.md` and existing acoustic code before implementation.
- Confirmed A14 requires non-rectangular rooms to distinguish unsupported vs explicit rectangular approximation; no silent solver substitution is allowed.
- Confirmed F5 is 10,000 analysis markers plus a later 64^3 scalar grid, with measured performance budget rather than a guessed target.

## Existing code finding

`backend/src/htdt/acoustics.py` already contains useful pure geometry algorithms:

- rectangular room modes;
- first-order image-source reflection points/path lengths;
- explicit `predicted_geometry_candidate` classification and assumptions.

The implementation deliberately does not model reflection amplitude/phase, absorption, speaker directivity, modal damping/amplitude, or a spatial SPL field. Therefore N70 must not render these outputs as a validated FR/heatmap.

## N70a implementation decision

First build a native immutable prediction authority and geometry visualization layer:

1. bind each prediction run to exact native SceneRevision/content hash plus model ID/version/parameters;
2. use a native adapter to reuse the existing Qt-free room-mode/reflection geometry;
3. reject non-rectangular rooms for the exact rectangular model;
4. keep any future rectangular approximation explicit and persisted;
5. add prediction-specific stale/cancel tokens rather than changing accepted N60 measurement-job semantics;
6. add `PredictionWorkspaceWindow` over N60 with a `予測` tab and non-pickable overlays;
7. enable heatmap/slice/volume only when a real model result contains a scalar field.

Detailed contract: [N70 design](N70_DESIGN.md).

## N70a implemented so far

Commit `305a05c238e0a01b4faecbda6e3c826d8cbffde5` added the immutable native prediction authority:

- `CadPredictionResult` with exact SceneRevision/content hash, model ID/version, canonical parameters, canonical input snapshot and SHA-256 input hash;
- separate SQLite prediction repository in the existing native CAD database;
- exact axis-aligned rectangle detection including shifted polygon rectangles;
- explicit `unsupported` results for non-rectangular polygon rooms with no silent rectangular approximation;
- world-coordinate first-order reflection identities and room-mode candidates;
- prediction-specific stale/cancel/document/constraint guard;
- focused repository, geometry compatibility and guard tests.

Commit `332ec93803b3bec981a605ca19f483051d02a86c` added the native prediction workspace:

- canonical request-identity helper used before async submission and checked again against completed model output;
- Japanese `予測` dock integrated into the single right-side CAD tab stack;
- saved prediction history and model/assumption/compatibility/input-revision display;
- GUI-thread-free prediction task with cancel/stale/document/constraint rejection before persistence/application;
- saved predictions are only overlaid when the current scene content hash matches the source input revision;
- direct path + first-order reflection path/point overlays are analysis actors and non-pickable;
- room-mode frequencies are listed as predicted geometry only, not rendered as a fake spatial field;
- heatmap/slice/volume control remains disabled until a real scalar-field result exists;
- native launcher now composes `PredictionWorkspaceWindow` while preserving N40-N60 inheritance.

CI #307 / run `35231396558` passed completely on Windows after the N70a workspace integration, including backend tests, native launcher import, existing acceptance-harness compile, PowerShell syntax, frontend build and smoke test.

Commit `32cc06be125a054416df4c6ebf9c0bf12560f7df` added `scripts/validate_n70_windows.py` for owned-Windows A13/A14 acceptance preparation. CI #308 / run `35231929534` passed completely, including compile of the new harness.

## A13/A14 acceptance preparation

`scripts/validate_n70_windows.py` exercises the production prediction workspace with real mouse/tab/button operations and controlled worker timing:

- A13: start prediction, edit/save scene while job is pending, verify stale completion is not saved/applied;
- A13: deterministic explicit cancel, delayed completion, document-ID switch and close-with-worker checks;
- A14: run the rectangular-only model on the 8-vertex L-room fixture and verify `unsupported`, no payload, no silent rectangular approximation and no prediction overlay;
- A14: verify scalar-field visualization remains gated while no scalar field exists.

The harness is compile-only in CI. RDC remains reserved for the final owned-Windows acceptance after the remaining N70 implementation slices are green.

## F5 bulk analysis-marker slice

N70 uses a reusable bulk marker primitive instead of tying candidate-cloud rendering to legacy O10 Context authority:

- `analysis_marker_polydata()` converts arbitrary native-domain `N×3` points to one render-space `PyVista.PolyData`;
- `render_analysis_marker_cloud()` submits that cloud through exactly one `add_mesh()` call and marks the actor non-pickable;
- the focused test builds 10,000 points and fixes the structural invariant that the renderer uses one mesh actor rather than one actor per marker;
- `scripts/benchmark_n70_f5_windows.py` builds F5 with 50 editable furniture objects plus 10,000 analysis markers, records first-render time and 40-frame orbit p50/p95/max, and checks that the marker cloud adds exactly one non-pickable actor;
- the first owned-PC run is deliberately measure-only. The F5 regression budget will be derived from the observed hardware result rather than invented before measurement.

The 64^3 scalar-grid part of F5 remains gated. N70a has no validated model that produces a scalar SPL field, so the product continues to disable heatmap/slice/volume controls instead of generating synthetic field data and treating it as prediction evidence.

Product commit `76c21eed7d7efcff23905e8af977854669df2752` contains the bulk-marker primitive and benchmark harness. CI #309 / run `35270706491` passed completely on Windows, including the new focused marker tests and benchmark-script compile. This SHA is frozen as the N70 owned-Windows product acceptance target.

## Owned-Windows gate preparation

`run-n70-hardware-gate.ps1` is kept separate from product code and pins `76c21eed7d7efcff23905e8af977854669df2752` as `ExpectedProductHead`.

The runner:

- refuses a dirty working tree;
- fetches the N70 branch and rejects unexpected product changes after the pinned SHA;
- records OS/build, CPU, RAM, active GPU/driver/display, AppliedDPI and Python/PySide6/PyVista/VTK/PyQtGraph versions;
- executes `validate_n70_windows.py` and `benchmark_n70_f5_windows.py` in one gate;
- cleans residual harness processes between phases;
- restores the exact original branch/detached SHA and requires a clean post-status even after failure.

CI performs a syntax check and preflight only. The actual A13/A14/F5 gate remains an owned-Windows task and will use one bundled RDC execution.

## Planned focused verification

- native SceneRevision/model/input immutable binding;
- result persistence round-trip;
- exact rectangular-room detection and non-rectangular rejection;
- acoustic-reference source/receiver mapping;
- underlying geometry algorithm outputs preserved without semantic promotion;
- prediction stale/cancel/document-switch guard;
- measured vs predicted UI semantics;
- reflection overlay identity and non-pickability;
- A13/A14 Windows harness compile before real-hardware gate;
- F5 10,000-marker one-actor invariant in CI and performance measurement on owned Windows.

## External model decision boundary

N70a does not require choosing a new external solver. REW Room Simulator / pyroomacoustics adoption is a later N70b decision boundary and requires S01/S03-equivalent evidence. Until then, the product exposes only what the current validated code actually computes: rectangular geometry candidates, not an SPL field.
