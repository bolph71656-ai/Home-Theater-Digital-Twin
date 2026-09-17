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
- Added `scripts/run-n60-hardware-gate.ps1` so the final owned-Windows gate can be executed as one RDC/mcp-bridge process: it checks/cleans only residual N60 harness processes, requires a clean repository, fetches the branch, verifies the accepted product-code SHA is still the product head, runs A12 then A13, records environment/version data, restores the original checkout, and verifies the post-run worktree is clean.
- Product composition is `MeasurementWorkspaceWindow -> MeasurementEditorWindow -> ConstraintEditorWindow -> ...`; existing CAD layers remain inherited rather than duplicated.

## High-DPI / real-interaction findings

Owned-Windows acceptance runs exposed interaction issues that CI compilation cannot reveal:

1. Early A12/A13 runs showed that actor-center viewport clicks became unreliable after the added right dock. Entity selection in the acceptance harness was changed to the visible scene tree while retaining real Win32 mouse input.
2. At 2880×1800 / 200% DPI, lower measurement controls were initially unreachable. A product `QScrollArea` wrapper was added instead of bypassing the UI from the harness.
3. Further diagnostics showed the scroll range itself existed, but the lower button global coordinate reached approximately `Y=1046`; the top-level window was exceeding the usable logical desktop. The right-side `制約` / `実測` docks are also tabified, so the harness now selects the `実測` tab with real mouse input before using its controls.
4. Product head `acfb0596691a3132cb9d096c49e708177598a9d5` makes the measurement scroll area's vertical size hint ignorable by the parent layout, keeps the full form as scrollable content, and clamps initial window size to `QScreen.availableGeometry()` with margin. This is a product usability fix, not an acceptance bypass.

The acceptance harness still requires actual OS mouse clicks for the relevant controls. Programmatic scrolling/tab lookup is used only to expose the same controls a user would navigate to; the product callbacks are not invoked directly.

## GitHub verification

Latest product head before final hardware rerun: `acfb0596691a3132cb9d096c49e708177598a9d5`.

GitHub Actions CI #280 / run `35214514448` completed successfully on that exact head. It passed:

- backend dependency install
- backend tests
- backend launcher CLI
- native CAD launcher CLI
- Windows CAD acceptance harness compilation, including A12/A13
- PowerShell syntax validation
- frontend install/build
- built frontend smoke test

Earlier diagnostic/product heads also passed CI while the real 200% DPI interaction problem was being isolated; CI success alone is not treated as A12/A13 acceptance.

After product head `acfb0596...`, branch-only changes are restricted to N60 progress documentation and the one-shot hardware-gate runner. That runner deliberately refuses acceptance if another product file changes after the declared product head, forcing the accepted product SHA to be updated instead of silently testing stale code.

## Windows acceptance status

A12/A13 are **not yet marked PASS**.

The most recent completed diagnostic run before the final product-size fix established:

- A12 immutable revision binding, offline FR, mouse move/save B, and historical ghost were already working.
- The A/B save click did not reach the intended visible control because the overall window extended below the usable desktop.
- A13 similarly failed to start the delayed REW job; diagnostics showed the REW control's center at the same out-of-desktop Y coordinate and the selection changed instead of the intended button receiving the click.
- The checkout was restored to the prior detached SHA and clean after that completed diagnostic run.

After `acfb0596...`, two bundled RDC attempts received no response from the authorized Windows device, including a follow-up residual-process check. Therefore the exact current local checkout/process state after those connection timeouts is **not re-confirmed** and must not be guessed. Do not merge PR #62 or close Issue #61 until the owned-Windows device is responsive and A12/A13 pass on the current product head.

## Remaining sequence

1. When RDC is responsive, invoke `scripts/run-n60-hardware-gate.ps1` in one mcp-bridge/RDC process where possible. The script performs residual N60-harness cleanup, clean-state verification, branch fetch/product-head validation, A12/A13 execution, environment capture, original-checkout restoration, and final clean-state verification.
2. Require A12 PASS for immutable A binding, offline FR, historical ghost, and saved comparison bound to exact A/B dataset + revision IDs.
3. Require A13 PASS for edit-stale rejection, UI responsiveness, explicit cancel, document-state change rejection, and clean close with no live worker.
4. Only after the hardware gate passes, create `docs/N60_ACCEPTANCE_2026-09-17.md`, update `IMPLEMENTATION_STATUS.md` to N60 complete / N70 next, mark PR #62 ready, merge it, and close #61 as completed.

## Key risks / invariants

- Never attach an old measurement to whatever scene is current at display time.
- Do not use external REW UUID or filename as HTDT primary identity.
- Measurement point means acoustic reference/capsule position, not seat body center.
- Do not infer capture time, calibration, phase validity, routing, or SPL reference when unknown.
- N50 constraint workspace is mutable document state; any future job depending on it must capture a hash/snapshot at submission.
- Saved measurement evidence remains valid historical evidence after scene edits; only its relationship to the current revision changes.
- A cancelled/stale background result must not mutate current UI/scene state.
