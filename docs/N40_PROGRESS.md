# N40 implementation progress

Tracking: #55  
Branch: `feat/n40-theater-objects`

## 2026-09-17 — start

- Confirmed `main` head `51d7125103eb391a2645f394988aa650839b0dac`.
- Confirmed N30b is merged and A09 is complete.
- Re-read the N40 roadmap and A10 acceptance contract before implementation.
- Reviewed current `SceneEntity`, `WorkingDocument`, native editor, room editor, wall editor, and view-state contracts.
- Reuse decision: keep `SceneEntity` / `SceneDocument`, command history, accepted move/rotate gizmos, `EditorViewState` hide/lock, and `CadEditorWindow` as product composition.
- New N40 scope is limited to typed theater-object semantics, add/duplicate/property commands, palette/Inspector/rendering, persistence tests, and A10.
- Browser UI remains frozen.
- RDC has not been used. It is reserved for the final Windows A10 gate.

## 2026-09-17 — implementation

- Extended theater entities to speaker / seat / screen / furniture / AV equipment / measurement point while keeping physical body and acoustic reference semantics separate.
- Added body-local `acoustic_reference_offset_m` and exact world reference calculation.
- Added atomic add, duplicate, and property replacement command paths with Undo/Redo and stable IDs.
- Made the 3.0.2 template a single Undo unit without constraining later speaker roles.
- Added Japanese-first native object palette, object Inspector, differentiated viewport primitives, duplicate, and existing hide/lock integration.
- Split product composition into `cad_composition.py`, `theater_editor.py`, and `theater_workflow.py` so N30b room/wall guards remain isolated from N40 theater behavior.
- Added explicit `座席へ向ける` acoustic action. It updates only speaker `aim_xyz`, never body pose, and can update multiple speakers atomically in one Undo unit.
- Added focused domain/repository tests for physical dimensions, acoustic references, atomic add/property commands, speaker aim, Undo/Redo, and save/reopen exactness.
- Added `scripts/validate_n40_windows.py` for the mouse-first A10 flow and `scripts/validate_n40_precision_windows.py` for numeric dimension/role refinement and exact reopen.
- CI #211 passed on commit `644747e33de629e26aee72322a45755ca78b33e7` including backend tests, native launcher, and A10 harness compile.
- Latest acceptance-prep head is `3c9dcaf05497977e9e63cee89aef5bb398c6b42e`; CI #213 is the current final pre-hardware validation.
- Accidental placeholder Issues #57 and #58 were immediately closed as `not planned`; N40 tracking remains Issue #55 / PR #56.

## Current implementation sequence

1. ~~Extend N40 entity semantics and acoustic reference helper.~~
2. ~~Add add/duplicate/property commands to working document.~~
3. ~~Add focused domain/repository tests.~~
4. ~~Add native palette, dimensions/role/reference Inspector, and differentiated primitives.~~
5. ~~Compose with room/wall modes and Japanese UI.~~
6. ~~Add A10 harness and CI compile coverage.~~
7. Complete final pre-hardware CI on the latest head.
8. Run A10 core + numeric precision acceptance on owned Windows hardware using real mouse input, in one bundled RDC operation.
9. Record acceptance, update `IMPLEMENTATION_STATUS.md`, then merge.

## Open design risks

- Keep body pose separate from acoustic reference point; do not encode listener ear/reference as seat body origin.
- Do not let unknown speaker aim become known as a side effect of placement/duplicate/resize.
- Hide/lock must stay outside physical scene data.
- N40 must not bypass N30b stable wall/opening/constraint transaction rules.
- 3.0.2 is a template/fixture, not a closed speaker-role schema.
- `aim_xyz` is an explicit world direction, not a persistent target constraint; moving a speaker after aiming does not silently re-aim it.
