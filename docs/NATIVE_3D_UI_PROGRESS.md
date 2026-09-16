# Native 3D UI progress log

## 2026-09-16

- O20 batch-prediction work was preserved on `feat/o20-batch-prediction` before the GUI redesign.
- Native GUI track is isolated on `feat/native-3d-cad-ui`.
- Windows prototype confirmed PySide6 6.11.2 + PyVista 0.49.0 + PyVistaQt 0.13.1 + VTK 9.7.0 on Python 3.12.
- Prototype rendered the eight-vertex concave room, FL/C/FR, and MLP in a native Qt window.
- PyVista `AffineWidget3D` rendered and accepted CAD-style translation/rotation interaction on a speaker actor.
- `docs/NATIVE_3D_UI.md` records the architecture decision and interaction/data contracts.
- Initial `ContextDraft` model is being used to keep edits off the immutable stored Context until Save.
- Unknown speaker aim remains unknown after position-only edits; explicit rotation is required before writing an aim vector.

Next acceptance slice:
1. synchronize Scene-tree selection with viewport picking;
2. add speaker/MLP gizmo movement with grid snap;
3. add polygon vertex handles in Top view;
4. Inspector precision editing;
5. Undo/Redo;
6. Save as a new immutable Context revision;
7. Windows render and interaction smoke tests;
8. CI and review before merge.
