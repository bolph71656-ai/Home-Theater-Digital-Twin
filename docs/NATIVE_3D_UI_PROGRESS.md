# Native 3D UI progress log

## 2026-09-16

- O20 batch-prediction work was preserved on `feat/o20-batch-prediction` before the GUI redesign.
- Native GUI track is isolated on `feat/native-3d-cad-ui`.
- Windows prototype confirmed PySide6 6.11.2 + PyVista 0.49.0 + PyVistaQt 0.13.1 + VTK 9.7.0 on Python 3.12.
- Prototype rendered the eight-vertex concave room, FL/C/FR, and MLP in a native Qt window.
- PyVista `AffineWidget3D` rendered and accepted CAD-style translation/rotation interaction on a speaker actor.
- `docs/NATIVE_3D_UI.md` and `docs/NATIVE_3D_EDITOR_ARCHITECTURE.md` record the adopted architecture and interaction/data contracts.
- Initial `ContextDraft` model keeps edits off the immutable stored Context until Save.
- Unknown speaker aim remains unknown after position-only edits; explicit rotation is required before writing an aim vector.
- Native runtime dependencies are now pinned in `backend/pyproject.toml`.
- Draft PR #37 is the durable implementation/review record for this redesign.
- Initial spatial-draft tests cover deterministic metric snapping, move-without-inventing-aim, explicit aim normalization, and undo/redo.

Next acceptance slice:
1. implement the PySide6 main window with Scene tree / viewport / Inspector;
2. synchronize Scene-tree selection with viewport picking;
3. add speaker/MLP gizmo movement with grid snap;
4. add polygon vertex handles in Top view;
5. Inspector precision editing;
6. Undo/Redo integration;
7. Save as a new immutable Context revision;
8. Windows render and interaction smoke tests;
9. full CI and review before merge.

O20 remains paused until the native scene can inspect placement/search/prediction data effectively. G00/G10/O10 backend contracts remain authoritative and will be surfaced as native scene layers instead of being reimplemented in the renderer.
