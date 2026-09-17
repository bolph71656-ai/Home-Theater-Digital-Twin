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
- Historical placement ghost will load the exact saved SceneRevision, not copy coordinates from the mutable current scene.
- Async REW reads will capture document/revision/hash/measurement-point input and require token/current-context validation before UI apply.
- Browser UI remains frozen.
- RDC has not been used for N60; reserve it for final A12/A13 Windows gates.

## Planned sequence

1. Define immutable native measurement/dataset/job-token models.
2. Implement `CadMeasurementRepository` and content-addressed native raw assets.
3. Implement SceneRevision + acoustic-reference binding validation.
4. Implement REW API/text normalization adapters.
5. Add focused persistence/binding/stale-result tests.
6. Add native measurement workspace composition and FR dock.
7. Add historical SceneRevision ghost layer and A/B comparison.
8. Add cancellable REW read worker with stale-result guard.
9. Add A12/A13 Windows harnesses and CI compile coverage.
10. Run final Windows A12/A13 only after GitHub CI is green.

## Key risks

- Never attach an old measurement to whatever scene is current at display time.
- Do not use external REW UUID or filename as HTDT primary identity.
- Measurement point means acoustic reference/capsule position, not seat body center.
- Do not infer capture time, calibration, phase validity, routing, or SPL reference when unknown.
- N50 constraint workspace is mutable document state; any future job depending on it must capture a hash/snapshot at submission.
- Saved measurement evidence remains valid historical evidence after scene edits; only its relationship to the current revision changes.
- A cancelled/stale background result must not mutate current UI/scene state.
