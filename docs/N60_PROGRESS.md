# N60 implementation progress

Tracking: #61  
Branch: `feat/n60-measurement-workspace`

## 2026-09-17 — start

- N50 merged to `main` as `f37ffdf8a4c9e67894afb52d7750562812313b0d`; main status advanced through docs commit `160c62e77ca9e1a32510795bf93604a6e7a3fd44`.
- Re-read N60 roadmap plus A12/A13 acceptance contracts.
- Reviewed `MEASUREMENT_WORKFLOW.md`, `DATA_AND_ANALYSIS.md`, `rew_api.py`, `rew_parser.py`, `database.py`, `comparison.py`, and `cad_repository.py` before coding.
- Confirmed `RewApiClient.get_frequency_response_snapshot()` already provides a read-only stable REW snapshot guard.
- Confirmed `rew_parser.py` already preserves original FR grid, source SHA-256, phase status/warnings, and parser version.
- Confirmed the legacy Store persists raw assets, immutable FR arrays, quality/provenance fields, and comparison results, but its `contexts` history is separate from native `SceneRevision` and will not become the native authority.
- Confirmed `SceneRepository` provides immutable revision ID/document ID/content hash and is the correct native measurement binding target.
- Selected N60 architecture: new native measurement repository in the same `cad-scenes.sqlite3`, with FK to exact `scene_revisions.revision_id`; reuse REW/parser/comparison pure modules through adapters instead of migrating legacy Context history.
- Historical placement ghost loads the exact saved SceneRevision, not coordinates from the mutable current scene.
- Async REW reads capture document/revision/hash/measurement-point input and require token/current-context validation before UI apply.
- Browser UI remains frozen.

## Implemented

- Added frozen native measurement, FR dataset, and comparison models.
- Added `CadMeasurementRepository` in the native scene database with immutable FK binding to exact `SceneRevision`, content-addressed raw assets, dataset storage, source-revision validation, and saved A/B comparison provenance.
- Added REW API snapshot and REW text normalization adapters without making legacy `Context` authoritative.
- External REW UUID remains provenance only; it is not the HTDT primary key.
- Unknown SPL calibration/reference and unknown capture metadata remain unknown rather than inferred.
- Added `MeasurementJobGuard` with submission-time revision/document/hash/point snapshot, cancellation, supersession, and stale-result rejection.
- Added focused invariant tests for immutable binding, invalid revision/hash/point rejection, REW provenance identity, comparison revision binding, and stale/cancel guards.
- Added PyQtGraph 0.14.0 to the backend dependency set and Windows lock.
- Added native Japanese `実測` workspace with saved-measurement tree, provenance metadata, FR plot, REW text/API import, A/B comparison, difference plot, and exact-revision historical placement ghost.
- Saved FR display reads local immutable datasets and does not require REW to be running.
- Added QThread-based external REW reads; blocking REW I/O is not performed on the GUI thread.
- Added A12/A13 Windows acceptance harnesses and CI compile coverage.
- Added `scripts/run-n60-hardware-gate.ps1` so the owned-Windows gate can be driven from one mcp-bridge/RDC process: clean-state check, residual N60-harness cleanup, branch/product-head validation, environment capture, A12/A13, original-checkout restoration, and post-run clean verification.
- Added a CI-safe `-PreflightOnly` path so Windows Actions exercises the gate runner's Git output handling before scarce RDC execution.
- Product composition is `MeasurementWorkspaceWindow -> MeasurementEditorWindow -> ConstraintEditorWindow -> ...`; existing CAD layers remain inherited rather than duplicated.

## High-DPI / real-interaction findings

Owned-Windows acceptance runs exposed interaction issues that CI compilation cannot reveal:

1. Early A12/A13 runs showed that actor-center viewport clicks became unreliable after the added right dock. Entity selection in the acceptance harness was changed to the visible scene tree while retaining real Win32 mouse input.
2. At 2880×1800 / 200% DPI, lower measurement controls were initially unreachable. A product `QScrollArea` wrapper was added instead of bypassing the UI from the harness.
3. Diagnostics showed the scroll range itself existed, but lower measurement controls still reached approximately `Y=1046` in Qt global coordinates. The `制約` / `実測` tab itself was correctly activated with real mouse input; the remaining problem was top-level/right-dock layout, not missing scrolling.
4. Product head `acfb0596691a3132cb9d096c49e708177598a9d5` made the measurement scroll area's vertical size hint ignorable and clamped the initial window to `QScreen.availableGeometry()`, but a later owned-Windows gate proved this was insufficient: the base `Inspector` remained in a separate right-side dock row above the tabified `オブジェクト詳細 / 制約 / 実測` row, so their vertical minimums were still additive.
5. Current product head `8d4bfcd4af7589ab51c1363407ed2d94d1f7ea79` unifies `Inspector / オブジェクト詳細 / 制約 / 実測` into one CAD-style right-side tab group, leaves the long measurement form internally scrollable, and re-clamps the window once after the first QMainWindow layout pass. This removes the structural source of the high-DPI vertical overflow instead of weakening the acceptance harness.

The acceptance harness still requires actual OS mouse clicks for the relevant controls. Programmatic scrolling/tab lookup is used only to expose the same controls a user would navigate to; product callbacks are not invoked directly.

## GitHub verification

Previous product head `acfb0596691a3132cb9d096c49e708177598a9d5` passed GitHub Actions CI #280 / run `35214514448` in full.

The gate-runner hardening path also passed Windows Actions:

- CI #283 / run `35217997514`: full PASS after introducing the one-shot runner.
- CI #284 / run `35218254883`: full PASS after detached/local-old-SHA launch support.
- CI #287 / run `35218671124`: full PASS including the first executable `Preflight N60 hardware gate runner` step.
- CI #288 / run `35218969089`: full PASS including `git fetch --dry-run` in preflight, covering Windows PowerShell's successful-git-stderr behavior that had failed on the real machine.

Current product-code head is `8d4bfcd4af7589ab51c1363407ed2d94d1f7ea79`; its CI must be green before the next real-hardware rerun. Branch changes after that product head are allowed only for the N60 gate runner, CI plumbing, and progress/acceptance documentation. The runner refuses acceptance if another product file changes after the declared product head.

## Windows acceptance status

A12/A13 are **not yet marked PASS**.

The owned Windows machine is responsive again. The one-shot gate established and preserved the real local state:

- original detached SHA: `5ede848e8e0b0967a50c04c83ff679a649ca439b`
- pre-run worktree: clean
- residual N60 harness processes before gate: none
- tested product SHA for the last completed product run: `acfb0596691a3132cb9d096c49e708177598a9d5`
- environment: Windows 11 Pro build 26200; Ryzen 7 8845HS / Radeon 780M; driver 32.0.13032.11; 2880×1800; AppliedDPI 192; Python 3.12.10; PySide6 6.11.2; PyVista 0.49.0; VTK 9.7.0; PyQtGraph 0.14.0
- restored SHA after run: `5ede848e8e0b0967a50c04c83ff679a649ca439b`
- post-run worktree: clean

Two earlier attempts stopped before A12/A13 because of runner-only Windows PowerShell issues: scalar unwrapping of one-line Git output, then successful `git fetch` stderr becoming terminating output under `$ErrorActionPreference='Stop'`. Both were fixed on GitHub and corresponding CI preflight coverage was added; neither attempt evaluated product behavior.

The first run that did reach the product (`acfb0596...`) produced:

```text
A12_PRODUCT_COMPOSITION True
A12_MOUSE_SELECT_SAVED_A False
A12_OFFLINE_FR False
A12_RESULT FAIL

A13_PRODUCT_COMPOSITION True
A13_REW_BUTTON_CLICKED_NO_TOKEN True
A13_REW_BUTTON ... center=1244,1046 ... viewport=564x434 ... vscroll=120/1102 panel_h=1536 ...
A13_START_STALE_JOB False
A13_RESULT FAIL
```

The repeated `Y=1046` finding confirmed that the remaining defect was the vertically split right context docks at 200% DPI. Product head `8d4bfcd...` addresses that layout. Do not merge PR #62 or close Issue #61 until A12/A13 pass on this newer product head.

## Remaining sequence

1. Require green CI for product head `8d4bfcd4af7589ab51c1363407ed2d94d1f7ea79` and the latest gate-runner/preflight head.
2. Run the owned-Windows gate again through the single bundled runner; do not perform separate RDC state probes because the runner owns cleanup/state capture/restoration.
3. Require A12 PASS for saved-A mouse selection/offline FR, immutable A binding, mouse move/save B, historical ghost, and saved comparison bound to exact A/B dataset + revision IDs.
4. Require A13 PASS for edit-stale rejection, UI responsiveness, explicit cancel, document-state change rejection, and clean close with no live worker.
5. Only after the hardware gate passes, create `docs/N60_ACCEPTANCE_2026-09-17.md`, update `IMPLEMENTATION_STATUS.md` to N60 complete / N70 next, mark PR #62 ready, merge it, and close #61 as completed.

## Key risks / invariants

- Never attach an old measurement to whatever scene is current at display time.
- Do not use external REW UUID or filename as HTDT primary identity.
- Measurement point means acoustic reference/capsule position, not seat body center.
- Do not infer capture time, calibration, phase validity, routing, or SPL reference when unknown.
- N50 constraint workspace is mutable document state; any future job depending on it must capture a hash/snapshot at submission.
- Saved measurement evidence remains valid historical evidence after scene edits; only its relationship to the current revision changes.
- A cancelled/stale background result must not mutate current UI/scene state.
