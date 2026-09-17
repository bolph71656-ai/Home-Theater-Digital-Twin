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

## Current implementation sequence

1. Extend N40 entity semantics and acoustic reference helper.
2. Add add/duplicate/property commands to working document.
3. Add focused domain/repository tests.
4. Add native palette, dimensions/role/reference Inspector, and differentiated primitives.
5. Compose with room/wall modes and Japanese UI.
6. Add A10 harness and CI compile coverage.
7. Run CI, fix only observed failures.
8. Run final A10 on owned Windows hardware using real mouse input.
9. Record acceptance, update `IMPLEMENTATION_STATUS.md`, then merge.

## Open design risks

- Keep body pose separate from acoustic reference point; do not encode listener ear/reference as seat body origin.
- Do not let unknown speaker aim become known as a side effect of placement/duplicate/resize.
- Hide/lock must stay outside physical scene data.
- N40 must not bypass N30b stable wall/opening/constraint transaction rules.
- 3.0.2 is a template/fixture, not a closed speaker-role schema.
